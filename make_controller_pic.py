#!/usr/bin/env python3
"""Build dualsense_controller.png, the picture patch_for_ps5.py puts in
Settings > Controls, from a photo of a DualSense.

    python make_controller_pic.py DualSense_Controller_Chroma_Pearl.jpg

The photo is "DualSense Controller Chroma Pearl.jpg" by Sonson2, CC BY-SA 4.0:
https://commons.wikimedia.org/wiki/File:DualSense_Controller_Chroma_Pearl.jpg

Needs Pillow (the patcher itself does not). The controller is cut
out of its background, placed on a 1024x670 canvas like the game's own
picture, and given a line from each button to the place where the page puts
that button's label (see LABEL_MOVES in patch_for_ps5.py).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'dualsense_controller.png')
SIZE = (1024, 670)
SCALE, OFFSET = 0.845, (20.7, 56.0)          # photo pixels -> canvas
SS = 3                                        # lines are drawn 3x and scaled down

# Outline of the controller in the photo (1152x774), clockwise from the top
# left, traced by hand. Its backdrop is too close in colour to key out.
OUTLINE = [
    (225, 85), (260, 67), (300, 58), (350, 54), (400, 52), (585, 50), (770, 52),
    (820, 54), (850, 54), (900, 60), (930, 72), (960, 100), (985, 140),
    (1005, 185), (1020, 240), (1032, 300), (1045, 370), (1050, 400), (1056, 500),
    (1057, 600), (1050, 650), (1035, 690), (1010, 705), (980, 715), (950, 717),
    (925, 700), (910, 660), (890, 600), (865, 540), (845, 492), (825, 462),
    (800, 452), (700, 452), (585, 452), (460, 450), (380, 452), (355, 462),
    (332, 492), (315, 530), (295, 580), (275, 630), (252, 695), (235, 707),
    (210, 710), (175, 705), (150, 692), (122, 650), (111, 600), (108, 500),
    (118, 400), (130, 350), (140, 300), (152, 250), (167, 195), (185, 145),
    (202, 110),
]

# Each line: where it leaves the picture (the label's place, as in the game's
# own picture), any corners, then the button, in canvas pixels.
LINES = {
    'L2':       [(268, 40), (268, 103)],
    'R2':       [(765, 40), (765, 103)],
    'L1':       [(125, 113), (222, 116)],
    'R1':       [(908, 113), (805, 116)],
    'Create':   [(83, 235), (112, 235), (212, 135), (300, 135), (323, 139)],
    'Up':       [(33, 285), (105, 285), (200, 166), (252, 172)],
    'Left':     [(5, 345), (108, 345), (207, 224)],
    'Down':     [(5, 437), (118, 437), (255, 273)],
    'Right':    [(10, 513), (150, 513), (312, 312), (308, 230)],
    'L3':       [(20, 600), (195, 600), (355, 362)],
    'R3':       [(430, 630), (430, 590), (560, 460), (614, 352)],
    'Options':  [(965, 235), (932, 235), (845, 132), (722, 132), (705, 137)],
    'Triangle': [(985, 302), (950, 302), (878, 190), (790, 168)],
    'Circle':   [(1005, 380), (960, 380), (848, 234)],
    'Cross':    [(1020, 453), (950, 453), (789, 289)],
    'Square':   [(1010, 548), (920, 548), (716, 344), (713, 244)],
}


def cut_out(photo):
    """The controller with a soft-edged alpha, everything else transparent."""
    inside = Image.new('L', photo.size, 0)
    ImageDraw.Draw(inside).polygon(OUTLINE, fill=255)
    # round the corners of the traced outline, pull it in a little to lose
    # the backdrop's fringe, then feather it
    inside = inside.filter(ImageFilter.GaussianBlur(4)).point(lambda v: 255 * (v > 127))
    alpha = inside.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    out = photo.convert('RGBA')
    out.putalpha(alpha)
    return out


def main():
    photo = Image.open(sys.argv[1])
    if photo.size != (1152, 774):
        raise SystemExit('expected the 1152x774 photo, got %dx%d' % photo.size)
    pad = cut_out(photo)
    pad = pad.resize((round(pad.width * SCALE), round(pad.height * SCALE)), Image.LANCZOS)
    canvas = Image.new('RGBA', SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(pad, (round(OFFSET[0]), round(OFFSET[1])))

    lines = Image.new('RGBA', (SIZE[0] * SS, SIZE[1] * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lines)
    for width, radius, colour in ((8, 9.5, (20, 22, 28, 255)), (3.5, 6.5, (255, 255, 255, 255))):
        for points in LINES.values():
            pts = [(x * SS, y * SS) for x, y in points]
            draw.line(pts, fill=colour, width=round(width * SS), joint='curve')
            for x, y in pts[:1] + pts[-1:]:
                r = (radius if (x, y) == pts[-1] else width / 2.0) * SS
                draw.ellipse((x - r, y - r, x + r, y + r), fill=colour)
    canvas.alpha_composite(lines.resize(SIZE, Image.LANCZOS))
    canvas.save(OUT, optimize=True)
    print(OUT, os.path.getsize(OUT), 'bytes')


if __name__ == '__main__':
    main()
