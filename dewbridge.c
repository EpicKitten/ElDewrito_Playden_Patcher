/*
 * dewbridge: gives ElDewrito 0.7.1's web UI its window.dewQuery bridge when the
 * embedded browser (CEF, Chromium 101) runs with --single-process.
 *
 * Normally custom_menu.exe, running as the renderer process, installs
 * window.dewQuery / window.dewQueryCancel (CEF's message router, renderer
 * side). In single-process mode that program never runs, so the pages cannot
 * call the game. This DLL takes binkw32.dll's place (it forwards every Bink
 * export to binkw32_orig.dll), hooks mtndew.dll's delay-loaded cef_initialize,
 * and adds a render process handler to the game's CefApp that speaks the same
 * process-message protocol as the router's browser side inside mtndew.dll.
 *
 * It also draws PS5 button glyphs into the game's fonts as they are loaded
 * (see dewfont.c), if dewbridge_ps5_glyphs.txt is in the game folder.
 *
 * Freestanding: no C runtime, kernel32 only. 32-bit x86.
 */

typedef unsigned int size_t;
typedef unsigned short char16;
typedef unsigned long DWORD;
typedef void *HANDLE;
typedef int BOOL;

#define WINAPI __stdcall
#define CB __stdcall /* CEF_CALLBACK */

__declspec(dllimport) HANDLE WINAPI GetModuleHandleA(const char *);
__declspec(dllimport) void *WINAPI GetProcAddress(HANDLE, const char *);
__declspec(dllimport) BOOL WINAPI VirtualProtect(void *, size_t, DWORD, DWORD *);
__declspec(dllimport) void WINAPI OutputDebugStringA(const char *);
__declspec(dllimport) HANDLE WINAPI CreateFileA(const char *, DWORD, DWORD, void *, DWORD, DWORD, HANDLE);
__declspec(dllimport) BOOL WINAPI WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
__declspec(dllimport) DWORD WINAPI SetFilePointer(HANDLE, long, long *, DWORD);
__declspec(dllimport) BOOL WINAPI CloseHandle(HANDLE);

/* ---- CEF C API, branch 4951 layouts (only what is used is named) ---- */

typedef struct { char16 *str; size_t length; void (*dtor)(char16 *); } cef_string_t;
typedef cef_string_t *cef_string_userfree_t;

typedef struct _base {
	size_t size;
	void (CB *add_ref)(struct _base *);
	int (CB *release)(struct _base *);
	int (CB *has_one_ref)(struct _base *);
	int (CB *has_at_least_one_ref)(struct _base *);
} base_t;

struct _rph;
typedef struct _app {
	base_t base;
	void *on_before_command_line_processing;
	void *on_register_custom_schemes;
	void *get_resource_bundle_handler;
	void *get_browser_process_handler;
	struct _rph *(CB *get_render_process_handler)(struct _app *);
} app_t;

typedef struct _list {
	base_t base;
	void *pad1[12];                                        /* is_valid .. get_value */
	int (CB *get_bool)(struct _list *, size_t);
	int (CB *get_int)(struct _list *, size_t);
	void *get_double;
	cef_string_userfree_t (CB *get_string)(struct _list *, size_t);
	void *pad2[5];                                         /* get_binary .. set_null */
	int (CB *set_bool)(struct _list *, size_t, int);
	int (CB *set_int)(struct _list *, size_t, int);
	void *set_double;
	int (CB *set_string)(struct _list *, size_t, const cef_string_t *);
	void *pad3[3];
} list_t;

typedef struct _msg {
	base_t base;
	void *is_valid, *is_read_only, *copy;
	cef_string_userfree_t (CB *get_name)(struct _msg *);
	list_t *(CB *get_argument_list)(struct _msg *);
} msg_t;

struct _v8ctx;
typedef struct _frame {
	base_t base;
	void *pad1[21];                                        /* is_valid .. get_browser */
	struct _v8ctx *(CB *get_v8context)(struct _frame *);
	void *visit_dom, *create_urlrequest;
	void (CB *send_process_message)(struct _frame *, int, msg_t *);
} frame_t;

typedef struct _v8val {
	base_t base;
	void *pad1[12];                                        /* is_valid .. is_array_buffer */
	int (CB *is_function)(struct _v8val *);
	void *is_same;
	int (CB *get_bool_value)(struct _v8val *);
	int (CB *get_int_value)(struct _v8val *);
	void *get_uint_value, *get_double_value, *get_date_value;
	cef_string_userfree_t (CB *get_string_value)(struct _v8val *);
	void *pad2[10];                                        /* is_user_created .. delete_value_byindex */
	struct _v8val *(CB *get_value_bykey)(struct _v8val *, const cef_string_t *);
	void *get_value_byindex;
	int (CB *set_value_bykey)(struct _v8val *, const cef_string_t *, struct _v8val *, int);
	void *pad3[12];                                        /* set_value_byindex .. get_function_handler */
	struct _v8val *(CB *execute_function)(struct _v8val *, struct _v8val *, size_t, struct _v8val *const *);
	void *execute_function_with_context;
} v8val_t;

typedef struct _v8ctx {
	base_t base;
	void *get_task_runner, *is_valid, *get_browser;
	frame_t *(CB *get_frame)(struct _v8ctx *);
	v8val_t *(CB *get_global)(struct _v8ctx *);
	int (CB *enter)(struct _v8ctx *);
	int (CB *exit)(struct _v8ctx *);
	void *is_same;
	int (CB *eval)(struct _v8ctx *, const cef_string_t *, const cef_string_t *, int, v8val_t **, base_t **);
} v8ctx_t;

typedef struct _v8handler {
	base_t base;
	int (CB *execute)(struct _v8handler *, const cef_string_t *, v8val_t *, size_t, v8val_t *const *, v8val_t **, cef_string_t *);
} v8handler_t;

typedef struct _rph {
	base_t base;
	void (CB *on_web_kit_initialized)(struct _rph *);
	void (CB *on_browser_created)(struct _rph *, base_t *, base_t *);
	void (CB *on_browser_destroyed)(struct _rph *, base_t *);
	base_t *(CB *get_load_handler)(struct _rph *);
	void (CB *on_context_created)(struct _rph *, base_t *, frame_t *, v8ctx_t *);
	void (CB *on_context_released)(struct _rph *, base_t *, frame_t *, v8ctx_t *);
	void (CB *on_uncaught_exception)(struct _rph *, base_t *, base_t *, base_t *, base_t *, base_t *);
	void (CB *on_focused_node_changed)(struct _rph *, base_t *, base_t *, base_t *);
	int (CB *on_process_message_received)(struct _rph *, base_t *, frame_t *, int, msg_t *);
} rph_t;

_Static_assert(sizeof(app_t) == 40, "app");
_Static_assert(sizeof(rph_t) == 56, "rph");
_Static_assert(sizeof(msg_t) == 40, "msg");
_Static_assert(sizeof(frame_t) == 120, "frame");
_Static_assert(sizeof(v8ctx_t) == 56, "v8ctx");
_Static_assert(sizeof(v8val_t) == 208, "v8val");
_Static_assert(sizeof(list_t) == 132, "list");

/* libcef.dll exports (cdecl), resolved once the library is loaded */
static v8val_t *(*cef_v8value_create_function)(const cef_string_t *, v8handler_t *);
static v8val_t *(*cef_v8value_create_int)(int);
static v8val_t *(*cef_v8value_create_bool)(int);
static v8val_t *(*cef_v8value_create_string)(const cef_string_t *);
static v8ctx_t *(*cef_v8context_get_current_context)(void);
static msg_t *(*cef_process_message_create)(const cef_string_t *);
static void (*cef_string_userfree_utf16_free)(cef_string_userfree_t);

/* ---- small helpers ---- */

void *memset(void *d, int c, size_t n) { unsigned char *p = d; while (n--) *p++ = (unsigned char)c; return d; }
void *memcpy(void *d, const void *s, size_t n) { unsigned char *p = d; const unsigned char *q = s; while (n--) *p++ = *q++; return d; }

static size_t slen(const char *s) { size_t n = 0; while (s[n]) n++; return n; }
static int streq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static int strieq(const char *a, const char *b)
{
	for (;; a++, b++) {
		char x = *a, y = *b;
		if (x >= 'A' && x <= 'Z') x += 32;
		if (y >= 'A' && y <= 'Z') y += 32;
		if (x != y) return 0;
		if (!x) return 1;
	}
}

static void logline(const char *text, unsigned value, int with_value)
{
	char buf[200];
	size_t n = 0;
	const char *p = "dewbridge: ";
	DWORD wrote;
	HANDLE h;

	while (*p) buf[n++] = *p++;
	while (*text && n < 170) buf[n++] = *text++;
	if (with_value) {
		static const char hex[] = "0123456789abcdef";
		int i;
		buf[n++] = ' '; buf[n++] = '0'; buf[n++] = 'x';
		for (i = 28; i >= 0; i -= 4) buf[n++] = hex[(value >> i) & 15];
	}
	buf[n++] = '\r'; buf[n++] = '\n'; buf[n] = 0;
	OutputDebugStringA(buf);
	h = CreateFileA("dewbridge.log", 0x40000000 /* GENERIC_WRITE */, 3, 0, 4 /* OPEN_ALWAYS */, 0x80, 0);
	if (h != (HANDLE)-1) {
		SetFilePointer(h, 0, 0, 2 /* FILE_END */);
		WriteFile(h, buf, (DWORD)n, &wrote, 0);
		CloseHandle(h);
	}
}

#define STR(name, lit) static const cef_string_t name = { (char16 *)u##lit, sizeof(u##lit) / 2 - 1, 0 }

STR(s_send, "__dewSend");
STR(s_cancel, "__dewCancel");
STR(s_recv, "__dewRecv");
STR(s_ctx, "__dewCtx");
STR(s_query_msg, "dewQueryMsg");
STR(s_cancel_msg, "dewQueryCancelMsg");
STR(s_glue_url, "dewbridge://glue");

static int cefstr_is(const cef_string_t *s, const cef_string_t *lit)
{
	size_t i;
	if (!s || s->length != lit->length) return 0;
	for (i = 0; i < s->length; i++) if (s->str[i] != lit->str[i]) return 0;
	return 1;
}

static void rel(void *o) { if (o) ((base_t *)o)->release((base_t *)o); }
static void *keep(void *o) { if (o) ((base_t *)o)->add_ref((base_t *)o); return o; }

/* The game's own render process handler. It exists but does not install the
 * bridge; every callback is still passed on to it. A callee owns the object
 * arguments it is given, so each is given its own reference. */
static struct _rph *game;

/* our own objects are static: reference counting does nothing */
static void CB ref_add(base_t *b) { (void)b; }
static int CB ref_release(base_t *b) { (void)b; return 0; }
static int CB ref_one(base_t *b) { (void)b; return 1; }

static int ready;      /* 1 usable, -1 disabled */
static int next_context = 1;

static int resolve(void)
{
	HANDLE cef;
	if (ready) return ready > 0;
	ready = -1;
	cef = GetModuleHandleA("libcef.dll");
	if (!cef) { logline("libcef.dll is not loaded", 0, 0); return 0; }
#define GET(n) if (!(n = GetProcAddress(cef, #n))) { logline("missing export " #n, 0, 0); return 0; }
	GET(cef_v8value_create_function)
	GET(cef_v8value_create_int)
	GET(cef_v8value_create_bool)
	GET(cef_v8value_create_string)
	GET(cef_v8context_get_current_context)
	GET(cef_process_message_create)
	GET(cef_string_userfree_utf16_free)
#undef GET
	ready = 1;
	return 1;
}

/* A struct libcef hands us must have the size these layouts assume. */
static int sized(void *o, size_t want, const char *what)
{
	if (o && ((base_t *)o)->size == want) return 1;
	if (ready > 0) {
		logline(what, o ? (unsigned)((base_t *)o)->size : 0, 1);
		logline("layout differs from CEF 4951: bridge disabled", 0, 0);
	}
	ready = -1;
	return 0;
}

/* ---- page -> game ---- */

static int CB native_execute(v8handler_t *self, const cef_string_t *name, v8val_t *object, size_t argc,
                             v8val_t *const *argv, v8val_t **retval, cef_string_t *exception)
{
	int handled = 0;
	size_t i;
	(void)self; (void)exception;

	if (ready > 0 && argc >= 2 && sized(argv[0], sizeof(v8val_t), "v8value size")) {
		int is_send = cefstr_is(name, &s_send);
		v8ctx_t *ctx = cef_v8context_get_current_context();
		if (ctx && sized(ctx, sizeof(v8ctx_t), "v8context size")) {
			frame_t *frame = ctx->get_frame(ctx);
			if (frame && sized(frame, sizeof(frame_t), "frame size")) {
				msg_t *msg = cef_process_message_create(is_send ? &s_query_msg : &s_cancel_msg);
				if (msg && sized(msg, sizeof(msg_t), "process message size")) {
					list_t *args = msg->get_argument_list(msg);
					if (args && sized(args, sizeof(list_t), "list size")) {
						args->set_int(args, 0, argv[0]->get_int_value(argv[0]));
						args->set_int(args, 1, argv[1]->get_int_value(argv[1]));
						if (is_send && argc >= 4) {
							cef_string_userfree_t req = argv[2]->get_string_value(argv[2]);
							args->set_string(args, 2, req);
							if (req) cef_string_userfree_utf16_free(req);
							args->set_bool(args, 3, argv[3]->get_bool_value(argv[3]));
						}
						rel(args);
						frame->send_process_message(frame, 0 /* PID_BROWSER */, msg);
						msg = 0; /* reference handed over */
						handled = 1;
					} else rel(args);
				}
				rel(msg);
			}
			rel(frame);
		}
		rel(ctx);
	}
	if (handled && retval) *retval = cef_v8value_create_bool(1);
	rel(object);
	for (i = 0; i < argc; i++) rel(argv[i]);
	return handled;
}

static v8handler_t g_native = { { sizeof(v8handler_t), ref_add, ref_release, ref_one, ref_one }, native_execute };

/* The page side of the router, in script. %CTX% is replaced by the context id. */
static const char16 glue_head[] = u"(function(){if(window.dewQuery)return;var ctx=";
static const char16 glue_tail[] =
	u",next=1,pend={},send=window.__dewSend,cancel=window.__dewCancel;"
	u"window.__dewCtx=ctx;"
	u"window.__dewRecv=function(id,ok,code,msg){var q=pend[id];if(!q)return;"
	u"if(!q.persistent||!ok)delete pend[id];"
	u"if(ok){if(q.onSuccess)q.onSuccess(msg);}else if(q.onFailure)q.onFailure(code,msg);};"
	u"window.dewQuery=function(o){"
	u"if(!o||typeof o.request!=='string')throw new Error(\"Invalid arguments; object member 'request' is required and must have type string\");"
	u"var id=next++;pend[id]={onSuccess:o.onSuccess,onFailure:o.onFailure,persistent:!!o.persistent};"
	u"send(ctx,id,o.request,!!o.persistent);return id;};"
	u"window.dewQueryCancel=function(id){if(pend[id]){delete pend[id];cancel(ctx,id);}};"
	u"})();";

static char16 glue_buf[sizeof(glue_head) / 2 + sizeof(glue_tail) / 2 + 16];

static void CB on_context_created(rph_t *self, base_t *browser, frame_t *frame, v8ctx_t *context)
{
	static int said;
	(void)self;
	if (!said) { said = 1; logline("first page context created", 0, 0); }
	if (game && game->on_context_created)
		game->on_context_created(game, keep(browser), keep(frame), keep(context));
	if (resolve() && sized(context, sizeof(v8ctx_t), "v8context size")) {
		context->enter(context);
		{
			v8val_t *global = context->get_global(context);
			if (global && sized(global, sizeof(v8val_t), "v8value size")) {
				cef_string_t code;
				v8val_t *ret = 0;
				base_t *exc = 0;
				size_t n = 0, i;
				int id = next_context++, div = 1000000000, started = 0;

				global->set_value_bykey(global, &s_send, cef_v8value_create_function(&s_send, &g_native), 0);
				global->set_value_bykey(global, &s_cancel, cef_v8value_create_function(&s_cancel, &g_native), 0);

				for (i = 0; i < sizeof(glue_head) / 2 - 1; i++) glue_buf[n++] = glue_head[i];
				for (; div; div /= 10) {
					int digit = (id / div) % 10;
					if (digit || started || div == 1) { glue_buf[n++] = (char16)('0' + digit); started = 1; }
				}
				for (i = 0; i < sizeof(glue_tail) / 2 - 1; i++) glue_buf[n++] = glue_tail[i];
				glue_buf[n] = 0;
				code.str = glue_buf; code.length = n; code.dtor = 0;
				if (!context->eval(context, &code, &s_glue_url, 1, &ret, &exc))
					logline("page glue failed in context", (unsigned)id, 1);
				rel(ret);
				rel(exc);
			}
			rel(global);
		}
		context->exit(context);
	}
	rel(browser); rel(frame); rel(context);
}

static void CB on_context_released(rph_t *self, base_t *browser, frame_t *frame, v8ctx_t *context)
{
	(void)self;
	/* Nothing is kept per page on this side, and a context that is going away
	 * is not entered: a reply for it finds no __dewRecv and is dropped. */
	if (game && game->on_context_released)
		game->on_context_released(game, keep(browser), keep(frame), keep(context));
	rel(browser); rel(frame); rel(context);
}

/* ---- game -> page ---- */

static int CB on_process_message_received(rph_t *self, base_t *browser, frame_t *frame, int source, msg_t *message)
{
	int handled = 0;
	(void)self; (void)source;

	if (ready > 0 && sized(message, sizeof(msg_t), "process message size") && sized(frame, sizeof(frame_t), "frame size")) {
		cef_string_userfree_t name = message->get_name(message);
		if (cefstr_is(name, &s_query_msg)) {
			list_t *args = message->get_argument_list(message);
			handled = 1;
			if (args && sized(args, sizeof(list_t), "list size")) {
				int request = args->get_int(args, 1);
				int ok = args->get_bool(args, 2);
				int code = ok ? 0 : args->get_int(args, 3);
				cef_string_userfree_t text = args->get_string(args, ok ? 3 : 4);
				v8ctx_t *ctx = frame->get_v8context(frame);
				if (ctx && sized(ctx, sizeof(v8ctx_t), "v8context size")) {
					ctx->enter(ctx);
					{
						v8val_t *global = ctx->get_global(ctx);
						v8val_t *recv = global ? global->get_value_bykey(global, &s_recv) : 0;
						if (recv && recv->is_function(recv)) {
							static const cef_string_t empty = { (char16 *)u"", 0, 0 };
							v8val_t *argv[4];
							v8val_t *ret;
							argv[0] = cef_v8value_create_int(request);
							argv[1] = cef_v8value_create_bool(ok);
							argv[2] = cef_v8value_create_int(code);
							argv[3] = cef_v8value_create_string(text ? text : &empty);
							ret = recv->execute_function(recv, 0, 4, argv); /* takes the four references */
							rel(ret);
						}
						rel(recv);
						rel(global);
					}
					ctx->exit(ctx);
				}
				rel(ctx);
				if (text) cef_string_userfree_utf16_free(text);
			}
			rel(args);
		}
		if (name) cef_string_userfree_utf16_free(name);
	}
	if (!handled && game && game->on_process_message_received)
		handled = game->on_process_message_received(game, keep(browser), keep(frame), source, keep(message));
	rel(browser); rel(frame); rel(message);
	return handled;
}

static void CB fwd_web_kit_initialized(rph_t *self)
{
	(void)self;
	if (game && game->on_web_kit_initialized) game->on_web_kit_initialized(game);
}

static void CB fwd_browser_created(rph_t *self, base_t *browser, base_t *extra)
{
	(void)self;
	if (game && game->on_browser_created) game->on_browser_created(game, keep(browser), keep(extra));
	rel(browser); rel(extra);
}

static void CB fwd_browser_destroyed(rph_t *self, base_t *browser)
{
	(void)self;
	if (game && game->on_browser_destroyed) game->on_browser_destroyed(game, keep(browser));
	rel(browser);
}

static base_t *CB fwd_get_load_handler(rph_t *self)
{
	(void)self;
	return game && game->get_load_handler ? game->get_load_handler(game) : 0;
}

static void CB fwd_uncaught_exception(rph_t *self, base_t *browser, base_t *frame, base_t *context, base_t *exception, base_t *trace)
{
	(void)self;
	if (game && game->on_uncaught_exception)
		game->on_uncaught_exception(game, keep(browser), keep(frame), keep(context), keep(exception), keep(trace));
	rel(browser); rel(frame); rel(context); rel(exception); rel(trace);
}

static void CB fwd_focused_node_changed(rph_t *self, base_t *browser, base_t *frame, base_t *node)
{
	(void)self;
	if (game && game->on_focused_node_changed)
		game->on_focused_node_changed(game, keep(browser), keep(frame), keep(node));
	rel(browser); rel(frame); rel(node);
}

static rph_t g_rph = {
	{ sizeof(rph_t), ref_add, ref_release, ref_one, ref_one },
	fwd_web_kit_initialized,
	fwd_browser_created,
	fwd_browser_destroyed,
	fwd_get_load_handler,
	on_context_created,
	on_context_released,
	fwd_uncaught_exception,
	fwd_focused_node_changed,
	on_process_message_received,
};

static rph_t *(CB *game_get_handler)(app_t *);

static rph_t *CB get_render_process_handler(app_t *self)
{
	static int asked;
	if (!asked) {
		asked = 1;
		game = game_get_handler ? game_get_handler(self) : 0; /* kept for the life of the process */
		if (game && game->base.size != sizeof(rph_t)) {
			logline("the game's render handler has an unexpected size", (unsigned)game->base.size, 1);
			game = 0;
		}
		logline("render process handler requested; game's own is", (unsigned)game, 1);
	}
	return &g_rph;
}

/* ---- the hook on mtndew.dll's delay-loaded cef_initialize ---- */

typedef int (*cef_initialize_t)(const void *, const void *, app_t *, void *);
static cef_initialize_t real_initialize; /* the delay-load thunk, then the real function */

static int hooked_initialize(const void *args, const void *settings, app_t *app, void *sandbox)
{
	if (app && app->base.size == sizeof(app_t)) {
		game_get_handler = app->get_render_process_handler;
		app->get_render_process_handler = get_render_process_handler;
		logline("render process handler added to the game's CefApp", 0, 0);
	} else
		logline("cef_app_t size differs from CEF 4951: bridge not installed", app ? (unsigned)app->base.size : 0, 1);
	return real_initialize(args, settings, app, sandbox);
}

static void install(void)
{
	unsigned char *base = (unsigned char *)GetModuleHandleA("mtndew.dll");
	unsigned char *pe;
	DWORD dir, *d;

	if (!base) { logline("mtndew.dll is not loaded: nothing hooked", 0, 0); return; }
	pe = base + *(DWORD *)(base + 0x3c);
	dir = *(DWORD *)(pe + 24 + 96 + 13 * 8); /* delay import directory */
	if (!dir) { logline("mtndew.dll has no delay imports", 0, 0); return; }

	/* ImgDelayDescr: attrs, name, hmod, iat, int, bound iat, unload iat, timestamp */
	for (d = (DWORD *)(base + dir); d[1]; d += 8) {
		DWORD bias = (d[0] & 1) ? (DWORD)base : 0; /* attrs bit 0: fields are RVAs */
		DWORD *iat, *names;

		if (!strieq((const char *)(bias + d[1]), "libcef.dll")) continue;
		iat = (DWORD *)(bias + d[3]);
		names = (DWORD *)(bias + d[4]);
		for (; *names; names++, iat++) {
			DWORD old;
			if (*names & 0x80000000) continue;
			if (!streq((const char *)(bias + *names + 2), "cef_initialize")) continue;
			real_initialize = (cef_initialize_t)*iat;
			if (!VirtualProtect(iat, 4, 4 /* PAGE_READWRITE */, &old)) { logline("cannot unprotect the import slot", 0, 0); return; }
			*iat = (DWORD)hooked_initialize;
			VirtualProtect(iat, 4, old, &old);
			logline("hooked mtndew.dll cef_initialize", 0, 0);
			return;
		}
	}
	logline("cef_initialize not found in mtndew.dll's delay imports", 0, 0);
}

/* ---- PS5 button glyphs in the game's fonts ---- */

#include "dewfont.c"

/* eldorado.exe 0.7.1, which always loads at 0x400000: the function that
 * checks a font block that has just been read. mtndew.dll's font loader calls
 * it for every block, whether the block came from font_package.bin or from a
 * mod's .pak. It starts: push ebp; mov ebp,esp; push ecx; push ebx; push esi;
 * mov esi,[ebp+8]. */
#define FONT_CHECK 0x65c880
#define GLYPH_SWITCH "dewbridge_ps5_glyphs.txt"
static const unsigned char font_check_head[] = { 0x55, 0x8b, 0xec, 0x51, 0x53, 0x56, 0x8b, 0x75, 0x08 };

/* the first four instructions of that function, then the rest of it */
__attribute__((naked)) static unsigned char game_font_check(__attribute__((unused)) unsigned char *block)
{
	__asm__("push %ebp; mov %esp, %ebp; push %ecx; push %ebx; push $0x65c885; ret");
}

static volatile long font_busy;

static unsigned char hooked_font_check(unsigned char *block)
{
	static int said;
	unsigned char ok = game_font_check(block);
	if (ok) {
		int n;
		while (__sync_lock_test_and_set(&font_busy, 1)) ;
		n = font_block_ps5(block);
		__sync_lock_release(&font_busy);
		if (n && said < 8) { said++; logline("PS5 glyphs drawn into a loaded font block:", (unsigned)n, 1); }
	}
	return ok;
}

static void install_fonts(void)
{
	unsigned char *at = (unsigned char *)FONT_CHECK;
	DWORD old;
	unsigned i;
	HANDLE h = CreateFileA(GLYPH_SWITCH, 0x80000000 /* GENERIC_READ */, 7, 0, 3 /* OPEN_EXISTING */, 0, 0);

	if (h == (HANDLE)-1) { logline("no " GLYPH_SWITCH ": fonts keep the button glyphs they have", 0, 0); return; }
	CloseHandle(h);
	if (GetModuleHandleA(0) != (HANDLE)0x400000) { logline("the game is not at 0x400000: fonts left alone", 0, 0); return; }
	for (i = 0; i < sizeof(font_check_head); i++)
		if (at[i] != font_check_head[i]) { logline("the font check is not the 0.7.1 code: fonts left alone", 0, 0); return; }
	if (!VirtualProtect(at, 5, 0x40 /* PAGE_EXECUTE_READWRITE */, &old)) { logline("cannot unprotect the font check", 0, 0); return; }
	at[0] = 0xe9; /* jmp hooked_font_check */
	*(DWORD *)(at + 1) = (DWORD)hooked_font_check - (FONT_CHECK + 5);
	VirtualProtect(at, 5, old, &old);
	logline("hooked the game's font check: button glyphs become PS5 ones as fonts load", 0, 0);
}

BOOL WINAPI DllMain(HANDLE module, DWORD reason, void *reserved)
{
	(void)module; (void)reserved;
	if (reason == 1 /* DLL_PROCESS_ATTACH */) { install(); install_fonts(); }
	return 1;
}
