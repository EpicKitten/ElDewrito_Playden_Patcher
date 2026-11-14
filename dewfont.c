/*
 * PS5 button glyphs for the fonts the game has in memory. Included by
 * dewbridge.c; uses nothing but memset and memcpy.
 *
 * The game keeps its fonts as 0x8000-byte blocks, read on demand from
 * maps/fonts/font_package.bin or, with a mod loaded, from the font package
 * inside the mod's .pak. A mod's package can redraw the button characters
 * (U+E100 and up) at its own sizes, and a .pak cannot be changed on disk: its
 * hash, which covers the fonts, is how the game and servers tell mods apart.
 * So the glyphs are replaced here, in each block as it is loaded.
 *
 * A block starts with 16-bit (table offset, character count), and the table
 * holds 32-bit (font << 16 | character, offset of the character). A character
 * is six 16-bit values (advance, packed size, width, height, origin x,
 * origin y) and its packed pixels:
 *
 *   00 hi lo   one pixel, ARGB4444; its colour stays current for what follows
 *   01..3f     that many transparent pixels
 *   40..7f     (byte & 3f) opaque pixels of the current colour
 *   80..bf     10aaalll: one pixel of the current colour, alpha a/7, then
 *              l = 1..3: 5 - l opaque pixels; l = 4..7: 9 - l transparent ones
 *   c0..ff     11aaabbb: two pixels of the current colour, alphas a/7 and b/7
 *
 * A PS5 glyph is scaled to fit the outline of the Xbox glyph it replaces,
 * keeping its own proportions, and written over it only if it packs into no
 * more bytes. Nothing else in the block moves.
 */

#include "dewglyphs.h"

#define FONT_BLOCK 0x8000
#define FONT_SIDE 128                   /* largest glyph handled, each way */

/* pixels as four bytes: alpha, red, green, blue, each 0..15 */
static unsigned char font_old[FONT_SIDE * FONT_SIDE * 4];
static unsigned char font_big[FONT_SIDE * FONT_SIDE * 4];
static unsigned char font_new[FONT_SIDE * FONT_SIDE * 4];
static unsigned char font_packed[FONT_BLOCK];

static unsigned font_u16(const unsigned char *p) { return p[0] | p[1] << 8; }
static unsigned font_u32(const unsigned char *p) { return font_u16(p) | font_u16(p + 2) << 16; }

/* Unpacks to at most max pixels. Returns the number of pixels the data
 * holds, or -1 if it holds more than max or ends in the middle of a code. */
static int font_unpack(const unsigned char *data, unsigned size, unsigned char *out, unsigned max)
{
	unsigned i = 0, n = 0, run, k;
	unsigned char r = 15, g = 15, b = 15;

#define PUT(alpha) do { if (n >= max) return -1; \
		out[4 * n] = (unsigned char)(alpha); out[4 * n + 1] = r; out[4 * n + 2] = g; out[4 * n + 3] = b; n++; } while (0)
	while (i < size) {
		unsigned code = data[i++];
		if (code == 0) {
			if (i + 2 > size) return -1;
			r = data[i] & 15; g = data[i + 1] >> 4; b = data[i + 1] & 15;
			PUT(data[i] >> 4);
			i += 2;
		} else if (code < 0x40) {
			for (k = 0; k < code; k++) PUT(0);
		} else if (code < 0x80) {
			for (k = 0; k < (code & 0x3f); k++) PUT(15);
		} else if (code < 0xc0) {
			PUT((((code >> 3) & 7) * 15 + 3) / 7);
			run = code & 7;
			if (run && run < 4) for (k = 0; k < 5 - run; k++) PUT(15);
			else if (run) for (k = 0; k < 9 - run; k++) PUT(0);
		} else {
			PUT((((code >> 3) & 7) * 15 + 3) / 7);
			PUT(((code & 7) * 15 + 3) / 7);
		}
	}
#undef PUT
	return (int)n;
}

/* Packs n pixels. Returns the packed length, or 0 if it is more than max. */
static unsigned font_pack(const unsigned char *px, unsigned n, unsigned char *out, unsigned max)
{
	unsigned i = 0, len = 0, j;
	int have = 0;
	unsigned char r = 0, g = 0, b = 0;

	while (i < n) {
		const unsigned char *p = px + 4 * i;
		if (len + 3 > max) return 0;
		if (p[0] == 0) {
			for (j = i; j < n && px[4 * j] == 0 && j - i < 0x3f; j++) ;
			out[len++] = (unsigned char)(j - i);
			i = j;
		} else if (!have || p[1] != r || p[2] != g || p[3] != b) {
			have = 1; r = p[1]; g = p[2]; b = p[3];
			out[len++] = 0;
			out[len++] = (unsigned char)(p[0] << 4 | r);
			out[len++] = (unsigned char)(g << 4 | b);
			i++;
		} else if (p[0] == 15) {
			for (j = i; j < n && px[4 * j] == 15 && px[4 * j + 1] == r && px[4 * j + 2] == g
					&& px[4 * j + 3] == b && j - i < 0x3f; j++) ;
			out[len++] = (unsigned char)(0x40 | (j - i));
			i = j;
		} else {
			unsigned a = (p[0] * 7 + 7) / 15;
			const unsigned char *q = i + 1 < n ? p + 4 : 0;
			if (q && (q[0] == 0 || (q[1] == r && q[2] == g && q[3] == b))) {
				out[len++] = (unsigned char)(0xc0 | a << 3 | (q[0] * 7 + 7) / 15);
				i += 2;
			} else {
				out[len++] = (unsigned char)(0x80 | a << 3);
				i++;
			}
		}
	}
	return len;
}

/* Draws the sw x sh picture src, scaled to dw x dh, at (x0, y0) of the
 * cleared w-wide picture dst. Each pixel is the mean of 4 x 4 samples. */
static void font_draw(const unsigned char *src, unsigned sw, unsigned sh,
                      unsigned char *dst, unsigned w, unsigned x0, unsigned y0, unsigned dw, unsigned dh)
{
	unsigned x, y, i, j;

	for (y = 0; y < dh; y++) {
		for (x = 0; x < dw; x++) {
			unsigned a = 0, r = 0, g = 0, b = 0;
			unsigned char *d = dst + 4 * ((y0 + y) * w + x0 + x);
			for (j = 0; j < 4; j++) {
				unsigned v = ((y * 4 + j) * 2 + 1) * sh / (dh * 8);
				for (i = 0; i < 4; i++) {
					unsigned u = ((x * 4 + i) * 2 + 1) * sw / (dw * 8);
					const unsigned char *s = src + 4 * (v * sw + u);
					a += s[0]; r += s[1] * s[0]; g += s[2] * s[0]; b += s[3] * s[0];
				}
			}
			d[0] = (unsigned char)((a + 8) / 16);
			if (d[0]) {
				d[1] = (unsigned char)((r + a / 2) / a);
				d[2] = (unsigned char)((g + a / 2) / a);
				d[3] = (unsigned char)((b + a / 2) / a);
			}
		}
	}
}

/* Replaces the Xbox button glyphs of one loaded, valid font block with PS5
 * ones. Returns how many were replaced. Not reentrant. */
static int font_block_ps5(unsigned char *block)
{
	unsigned table = font_u16(block), count = font_u16(block + 2), n, k;
	int done = 0;

	if (table + 8 * count > FONT_BLOCK) return 0;
	for (n = 0; n < count; n++) {
		unsigned character = font_u32(block + table + 8 * n) & 0xffff;
		unsigned offset = font_u32(block + table + 8 * n + 4);
		unsigned size, w, h, x, y, x0, y0, x1, y1, bw, bh, dw, dh, variant;
		unsigned char *glyph;
		const struct font_master *masters = 0;

		for (k = 0; k < sizeof(font_characters) / sizeof(font_characters[0]); k++)
			if (font_characters[k].character == character) masters = font_masters[font_characters[k].master];
		if (!masters || offset > FONT_BLOCK - 12) continue;
		glyph = block + offset;
		size = font_u16(glyph + 2); w = font_u16(glyph + 4); h = font_u16(glyph + 6);
		if (offset + 12 + size > FONT_BLOCK || w < 8 || w > FONT_SIDE || h < 8 || h > FONT_SIDE) continue;
		if (font_unpack(glyph + 12, size, font_old, w * h) != (int)(w * h)) continue;

		/* the part of the bitmap the Xbox glyph is drawn on */
		x0 = w; y0 = h; x1 = 0; y1 = 0;
		for (y = 0; y < h; y++)
			for (x = 0; x < w; x++)
				if (font_old[4 * (y * w + x)]) {
					if (x < x0) x0 = x;
					if (x >= x1) x1 = x + 1;
					if (y < y0) y0 = y;
					if (y >= y1) y1 = y + 1;
				}
		if (x1 <= x0 || y1 <= y0) continue;
		bw = x1 - x0; bh = y1 - y0;

		for (variant = 0; variant < 2 && masters[variant].data; variant++) {
			const struct font_master *m = &masters[variant];
			unsigned len;
			if (font_unpack(m->data, m->size, font_big, m->w * m->h) != m->w * m->h) continue;
			if (bw * m->h <= bh * m->w) { dw = bw; dh = (m->h * bw + m->w / 2) / m->w; }
			else { dh = bh; dw = (m->w * bh + m->h / 2) / m->h; }
			if (!dw) dw = 1;
			if (!dh) dh = 1;
			memset(font_new, 0, w * h * 4);
			font_draw(font_big, m->w, m->h, font_new, w, x0 + (bw - dw) / 2, y0 + (bh - dh) / 2, dw, dh);
			len = font_pack(font_new, w * h, font_packed, size);
			if (!len) continue;
			memcpy(glyph + 12, font_packed, len);
			memset(glyph + 12 + len, 0, size - len);
			glyph[2] = (unsigned char)len; glyph[3] = (unsigned char)(len >> 8);
			done++;
			break;
		}
	}
	return done;
}
