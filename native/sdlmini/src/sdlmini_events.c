/*
 * SDLmini - events, keyboard, mouse, cursor and window-manager stubs.
 *
 * amiga_gfx.c hands us Intuition messages already reduced to four kinds
 * (move, button down/up, raw key, quit, resize). Everything SDL-shaped is
 * built here: the queue, the key table, the modifier and button state.
 *
 * Raw key codes are the Amiga keyboard matrix, not ASCII. The table below is
 * the same one the openttd_amiga_68k video driver uses, retargeted from
 * OpenTTD key codes to SDLK_* values.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "SDL_syswm.h"
#include "sdlmini.h"
#include "amiga_gfx.h"

/* ------------------------------------------------------------ key table -- */

typedef struct {
	int    raw;        /* Amiga raw key code, bit 7 clear */
	int    sym;        /* SDLK_* */
	char   ascii;      /* unshifted character, 0 for none */
	char   shifted;    /* shifted character, 0 for none */
} AmigaKey;

static const AmigaKey s_keys[] = {
	{ 0x45, SDLK_ESCAPE,    0,   0   },
	{ 0x41, SDLK_BACKSPACE, 0,   0   },
	{ 0x46, SDLK_DELETE,    0,   0   },
	{ 0x44, SDLK_RETURN,    0,   0   },
	{ 0x43, SDLK_RETURN,    0,   0   },   /* keypad Enter */
	{ 0x42, SDLK_TAB,       0,   0   },
	{ 0x40, SDLK_SPACE,    ' ', ' '  },
	{ 0x4C, SDLK_UP,        0,   0   },
	{ 0x4D, SDLK_DOWN,      0,   0   },
	{ 0x4E, SDLK_RIGHT,     0,   0   },
	{ 0x4F, SDLK_LEFT,      0,   0   },
	{ 0x50, SDLK_F1,  0, 0 }, { 0x51, SDLK_F2,  0, 0 },
	{ 0x52, SDLK_F3,  0, 0 }, { 0x53, SDLK_F4,  0, 0 },
	{ 0x54, SDLK_F5,  0, 0 }, { 0x55, SDLK_F6,  0, 0 },
	{ 0x56, SDLK_F7,  0, 0 }, { 0x57, SDLK_F8,  0, 0 },
	{ 0x58, SDLK_F9,  0, 0 }, { 0x59, SDLK_F10, 0, 0 },

	{ 0x01, SDLK_1, '1', '!' }, { 0x02, SDLK_2, '2', '@' }, { 0x03, SDLK_3, '3', '#' },
	{ 0x04, SDLK_4, '4', '$' }, { 0x05, SDLK_5, '5', '%' }, { 0x06, SDLK_6, '6', '^' },
	{ 0x07, SDLK_7, '7', '&' }, { 0x08, SDLK_8, '8', '*' }, { 0x09, SDLK_9, '9', '(' },
	{ 0x0A, SDLK_0, '0', ')' }, { 0x0B, SDLK_MINUS, '-', '_' }, { 0x0C, SDLK_EQUALS, '=', '+' },

	{ 0x10, SDLK_q, 'q', 'Q' }, { 0x11, SDLK_w, 'w', 'W' }, { 0x12, SDLK_e, 'e', 'E' },
	{ 0x13, SDLK_r, 'r', 'R' }, { 0x14, SDLK_t, 't', 'T' }, { 0x15, SDLK_y, 'y', 'Y' },
	{ 0x16, SDLK_u, 'u', 'U' }, { 0x17, SDLK_i, 'i', 'I' }, { 0x18, SDLK_o, 'o', 'O' },
	{ 0x19, SDLK_p, 'p', 'P' },
	{ 0x1A, SDLK_LEFTBRACKET,  '[', '{' }, { 0x1B, SDLK_RIGHTBRACKET, ']', '}' },

	{ 0x20, SDLK_a, 'a', 'A' }, { 0x21, SDLK_s, 's', 'S' }, { 0x22, SDLK_d, 'd', 'D' },
	{ 0x23, SDLK_f, 'f', 'F' }, { 0x24, SDLK_g, 'g', 'G' }, { 0x25, SDLK_h, 'h', 'H' },
	{ 0x26, SDLK_j, 'j', 'J' }, { 0x27, SDLK_k, 'k', 'K' }, { 0x28, SDLK_l, 'l', 'L' },
	{ 0x29, SDLK_SEMICOLON, ';', ':' }, { 0x2A, SDLK_QUOTE, '\'', '"' },

	{ 0x31, SDLK_z, 'z', 'Z' }, { 0x32, SDLK_x, 'x', 'X' }, { 0x33, SDLK_c, 'c', 'C' },
	{ 0x34, SDLK_v, 'v', 'V' }, { 0x35, SDLK_b, 'b', 'B' }, { 0x36, SDLK_n, 'n', 'N' },
	{ 0x37, SDLK_m, 'm', 'M' },
	{ 0x38, SDLK_COMMA,  ',', '<' },
	{ 0x39, SDLK_PERIOD, '.', '>' },
	{ 0x3A, SDLK_SLASH,  '/', '?' },
	{ 0x00, SDLK_BACKQUOTE, '`', '~' },
	{ 0x0D, SDLK_BACKSLASH, '\\', '|' },

	/* Keypad, because the battlescape and the geoscape both use it. */
	{ 0x0F, SDLK_KP0, 0, 0 }, { 0x1D, SDLK_KP1, 0, 0 }, { 0x1E, SDLK_KP2, 0, 0 },
	{ 0x1F, SDLK_KP3, 0, 0 }, { 0x2D, SDLK_KP4, 0, 0 }, { 0x2E, SDLK_KP5, 0, 0 },
	{ 0x2F, SDLK_KP6, 0, 0 }, { 0x3D, SDLK_KP7, 0, 0 }, { 0x3E, SDLK_KP8, 0, 0 },
	{ 0x3F, SDLK_KP9, 0, 0 },
	{ 0x5A, SDLK_KP_DIVIDE,   0, 0 }, { 0x5B, SDLK_KP_MULTIPLY, 0, 0 },
	{ 0x4A, SDLK_KP_MINUS,    0, 0 }, { 0x5E, SDLK_KP_PLUS,     0, 0 },
	{ 0x3C, SDLK_KP_PERIOD,   0, 0 },

	/* Modifiers, so the game can also see them as ordinary key events. */
	{ 0x60, SDLK_LSHIFT, 0, 0 }, { 0x61, SDLK_RSHIFT, 0, 0 },
	{ 0x62, SDLK_CAPSLOCK, 0, 0 },
	{ 0x63, SDLK_LCTRL,  0, 0 },
	{ 0x64, SDLK_LALT,   0, 0 }, { 0x65, SDLK_RALT,   0, 0 },
	{ 0x66, SDLK_LSUPER, 0, 0 }, { 0x67, SDLK_RSUPER, 0, 0 },
	{ 0x5F, SDLK_HELP,   0, 0 },
};

/* ---------------------------------------------------------------- state -- */

#define QUEUE_SIZE 64

static SDL_Event s_queue[QUEUE_SIZE];
static int       s_head, s_tail;

static Uint8  s_ignore[SDL_NUMEVENTS];  /* SDL_IGNORE per event type */
static int    s_mouse_x, s_mouse_y;
static Uint8  s_buttons;                /* SDL_BUTTON(n) mask */
static SDLMod s_mods = KMOD_NONE;
static int    s_unicode_on;

/* A pointer warp asks Intuition to move the pointer, which then reports the
 * move back to us as an ordinary mouse-move message. Swallowing exactly one
 * such message keeps the game from seeing its own warp as player input - the
 * same trick amiga_v.cpp uses in the OpenTTD port. */
static int s_swallow_move;

static void queue_push(const SDL_Event *ev)
{
	int next = (s_tail + 1) % QUEUE_SIZE;
	if (s_ignore[ev->type]) return;

	/* AMIGA-PORT: collapse a run of mouse moves into the newest position.
	 * Only the latest position means anything to the game, but every queued
	 * one is handled separately - and on the geoscape one motion event costs
	 * hundreds of ms on a machine with an FPU (Globe::cartToPolar goes through
	 * the 68881 flavour of mathieeedoubtrans). That fed itself: the slower the
	 * handling, the more moves piled up, so a flick of the mouse froze the
	 * geoscape for 14-32 s (measured 2026-08-18). Relative motion is summed so
	 * drag-scrolling still travels the same distance. Real SDL coalesces the
	 * same way when the queue backs up. */
	if (ev->type == SDL_MOUSEMOTION && s_tail != s_head) {
		int last = (s_tail + QUEUE_SIZE - 1) % QUEUE_SIZE;
		if (s_queue[last].type == SDL_MOUSEMOTION) {
			Sint16 rx = (Sint16)(s_queue[last].motion.xrel + ev->motion.xrel);
			Sint16 ry = (Sint16)(s_queue[last].motion.yrel + ev->motion.yrel);
			s_queue[last] = *ev;
			s_queue[last].motion.xrel = rx;
			s_queue[last].motion.yrel = ry;
			return;
		}
	}

	if (next == s_head) return;             /* full: drop, never block */
	s_queue[s_tail] = *ev;
	s_tail = next;
}

/* AMIGA-PORT keyboard fix (0.5.5): the plain compare loop here was
 * miscompiled by gcc 6.5 at -O1 - the log showed `key raw 0x25 idx 36
 * entry.raw 0x13`: a search for 'h' RETURNED the 'r' entry, which is why
 * typing produced only 'r' (and '6') no matter the key. Same compiler bug
 * family as Mod.cpp (see build.sh). Rebuilt as a direct 128-entry map,
 * initialised once with volatile loads, and pinned to -O0. */
__attribute__((optimize(0)))
static const AmigaKey *lookup(int raw)
{
	static const AmigaKey *map[128];
	static int init = 0;
	if (!init) {
		volatile unsigned i;
		for (i = 0; i < sizeof(s_keys) / sizeof(s_keys[0]); i++) {
			const AmigaKey *e = &s_keys[i];
			volatile int r = e->raw;
			if (r >= 0 && r < 128) map[r] = e;
		}
		init = 1;
	}
	if (raw < 0 || raw >= 128) return NULL;
	return map[raw];
}

static void update_mods(int sym, int down)
{
	SDLMod bit = KMOD_NONE;
	switch (sym) {
		case SDLK_LSHIFT: bit = KMOD_LSHIFT; break;
		case SDLK_RSHIFT: bit = KMOD_RSHIFT; break;
		case SDLK_LCTRL:  bit = KMOD_LCTRL;  break;
		case SDLK_RCTRL:  bit = KMOD_RCTRL;  break;
		case SDLK_LALT:   bit = KMOD_LALT;   break;
		case SDLK_RALT:   bit = KMOD_RALT;   break;
		default: return;
	}
	if (down) s_mods = (SDLMod)(s_mods | bit);
	else      s_mods = (SDLMod)(s_mods & ~bit);
}

void SDLmini_SetMousePos(int x, int y)
{
	s_mouse_x = x;
	s_mouse_y = y;
}

/* ------------------------------------------------ injected (autoinput) -- */

/* Events that did not come from Intuition: the in-guest test driver
 * (sdlmini_autoinput.c) feeds these. They go through exactly the same
 * bookkeeping as real input so the game cannot tell the difference. */
void SDLmini_InjectMouseMove(int x, int y)
{
	SDL_Event ev;
	memset(&ev, 0, sizeof(ev));
	ev.type         = SDL_MOUSEMOTION;
	ev.motion.state = s_buttons;
	ev.motion.x     = (Uint16)x;
	ev.motion.y     = (Uint16)y;
	ev.motion.xrel  = (Sint16)(x - s_mouse_x);
	ev.motion.yrel  = (Sint16)(y - s_mouse_y);
	s_mouse_x = x;
	s_mouse_y = y;
	queue_push(&ev);
}

void SDLmini_InjectMouseButton(int button, int down)
{
	SDL_Event ev;
	memset(&ev, 0, sizeof(ev));
	if (down) s_buttons |= SDL_BUTTON(button);
	else      s_buttons &= ~SDL_BUTTON(button);
	ev.type          = (Uint8)(down ? SDL_MOUSEBUTTONDOWN : SDL_MOUSEBUTTONUP);
	ev.button.button = (Uint8)button;
	ev.button.state  = (Uint8)(down ? SDL_PRESSED : SDL_RELEASED);
	ev.button.x      = (Uint16)s_mouse_x;
	ev.button.y      = (Uint16)s_mouse_y;
	queue_push(&ev);
}

void SDLmini_InjectKey(int sym, int down)
{
	SDL_Event ev;
	memset(&ev, 0, sizeof(ev));
	update_mods(sym, down);
	ev.type              = (Uint8)(down ? SDL_KEYDOWN : SDL_KEYUP);
	ev.key.state         = (Uint8)(down ? SDL_PRESSED : SDL_RELEASED);
	ev.key.keysym.sym    = (SDLKey)sym;
	ev.key.keysym.mod    = s_mods;
	if (s_unicode_on && down && sym >= 32 && sym < 127)
		ev.key.keysym.unicode = (Uint16)sym;
	queue_push(&ev);
}

/* ----------------------------------------------------------------- pump -- */

void SDLmini_AutoinputPoll(void);

/* TEMP (2026-08-18): the geoscape stalls for 10-50 s with an FPU present and
 * the whole stall lands outside think/blit/flip, i.e. in this pump. These
 * counters split it so one stalled frame is one complete answer. */
unsigned long SDLmini_ProfAuto = 0, SDLmini_ProfPump = 0;
unsigned long SDLmini_ProfEvents = 0, SDLmini_ProfPolls = 0;

void SDLmini_PumpEvents(void)
{
	AmigaGfxEvent ae;
	Uint32 pT_ = SDL_GetTicks();

	SDLmini_AutoinputPoll();
	SDLmini_ProfAuto += SDL_GetTicks() - pT_;
	++SDLmini_ProfPolls;
	pT_ = SDL_GetTicks();
	while (amigagfx_poll(&ae)) {
		++SDLmini_ProfEvents;
		SDL_Event ev;
		memset(&ev, 0, sizeof(ev));

		switch (ae.type) {
		case AMIGAGFX_EV_MOUSEMOVE: {
			int rx = ae.x - s_mouse_x;
			int ry = ae.y - s_mouse_y;
			s_mouse_x = ae.x;
			s_mouse_y = ae.y;
			if (s_swallow_move) { s_swallow_move = 0; break; }
			ev.type            = SDL_MOUSEMOTION;
			ev.motion.state    = s_buttons;
			ev.motion.x        = (Uint16)ae.x;
			ev.motion.y        = (Uint16)ae.y;
			ev.motion.xrel     = (Sint16)rx;
			ev.motion.yrel     = (Sint16)ry;
			queue_push(&ev);
			break;
		}

		case AMIGAGFX_EV_MOUSEDOWN:
		case AMIGAGFX_EV_MOUSEUP: {
			int down = (ae.type == AMIGAGFX_EV_MOUSEDOWN);
			Uint8 button = (ae.code == AMIGAGFX_BUTTON_RIGHT) ? SDL_BUTTON_RIGHT : SDL_BUTTON_LEFT;
			s_mouse_x = ae.x;
			s_mouse_y = ae.y;
			if (down) s_buttons |= SDL_BUTTON(button);
			else      s_buttons &= ~SDL_BUTTON(button);
			{
				char lb[96];
				snprintf(lb, sizeof(lb), "event: mouse button %d %s at %d,%d",
					(int)button, down ? "down" : "up", ae.x, ae.y);
				SDLmini_Log(lb);
			}
			ev.type          = (Uint8)(down ? SDL_MOUSEBUTTONDOWN : SDL_MOUSEBUTTONUP);
			ev.button.button = button;
			ev.button.state  = (Uint8)(down ? SDL_PRESSED : SDL_RELEASED);
			ev.button.x      = (Uint16)ae.x;
			ev.button.y      = (Uint16)ae.y;
			queue_push(&ev);
			break;
		}

		case AMIGAGFX_EV_KEY: {
			int raw  = ae.code & 0x7f;
			int down = ((ae.code & 0x80) == 0);
			const AmigaKey *k = lookup(raw);
			if (k == NULL) break;

			update_mods(k->sym, down);

			ev.type              = (Uint8)(down ? SDL_KEYDOWN : SDL_KEYUP);
			ev.key.state         = (Uint8)(down ? SDL_PRESSED : SDL_RELEASED);
			ev.key.keysym.sym    = (SDLKey)k->sym;
			ev.key.keysym.scancode = (Uint8)raw;
			ev.key.keysym.mod    = s_mods;
			{
				/* Keys are rare and every one of them can end the game
				 * (StartState quits on any key after a load error, the
				 * menus on Ctrl/Amiga+Q), so each is worth a log line. */
				/* Split across short lines on purpose: a single line with many
				 * varargs is exactly the shape this libc gets wrong (CLAUDE.md
				 * rule 4), and this log is being used to judge the lookup. */
				char lb[96];
				snprintf(lb, sizeof(lb), "event: key raw 0x%02x idx %d entry.raw 0x%02x",
					raw, (int)(k - s_keys), k->raw);
				SDLmini_Log(lb);
				snprintf(lb, sizeof(lb), "event: key sym %d ascii %d stride %d",
					(int)k->sym, (int)(unsigned char)k->ascii, (int)sizeof(AmigaKey));
				SDLmini_Log(lb);
				snprintf(lb, sizeof(lb), "event: key %s mods 0x%03x unicode_on %d",
					down ? "down" : "up", (unsigned)s_mods, s_unicode_on);
				SDLmini_Log(lb);
			}
			if (s_unicode_on && down) {
				char ch = (s_mods & KMOD_SHIFT) ? k->shifted : k->ascii;
				ev.key.keysym.unicode = (Uint16)(unsigned char)ch;
			}
			queue_push(&ev);
			break;
		}

		case AMIGAGFX_EV_QUIT:
			SDLmini_Log("event: QUIT (window close)");
			ev.type = SDL_QUIT;
			queue_push(&ev);
			break;

		case AMIGAGFX_EV_RESIZE:
			ev.type         = SDL_VIDEORESIZE;
			ev.resize.w     = ae.x;
			ev.resize.h     = ae.y;
			queue_push(&ev);
			break;

		default:
			break;
		}
	}
	SDLmini_ProfPump += SDL_GetTicks() - pT_;
}

void SDL_PumpEvents(void) { SDLmini_PumpEvents(); }

int SDL_PollEvent(SDL_Event *event)
{
	SDLmini_PumpEvents();
	if (s_head == s_tail) return 0;
	if (event != NULL) *event = s_queue[s_head];
	s_head = (s_head + 1) % QUEUE_SIZE;
	return 1;
}

int SDL_WaitEvent(SDL_Event *event)
{
	for (;;) {
		if (SDL_PollEvent(event)) return 1;
		SDLmini_Sleep(10);
	}
}

int SDL_PushEvent(SDL_Event *event)
{
	queue_push(event);
	return 0;
}

Uint8 SDL_EventState(Uint8 type, int state)
{
	Uint8 was;
	if (type >= SDL_NUMEVENTS) return SDL_IGNORE;
	was = (Uint8)(s_ignore[type] ? SDL_IGNORE : SDL_ENABLE);
	if (state == SDL_IGNORE) s_ignore[type] = 1;
	else if (state == SDL_ENABLE) s_ignore[type] = 0;
	return was;
}

/* --------------------------------------------------------------- input -- */

Uint8 SDL_GetMouseState(int *x, int *y)
{
	if (x != NULL) *x = s_mouse_x;
	if (y != NULL) *y = s_mouse_y;
	return s_buttons;
}

Uint8 SDL_GetRelativeMouseState(int *x, int *y)
{
	if (x != NULL) *x = 0;
	if (y != NULL) *y = 0;
	return s_buttons;
}

void SDL_WarpMouse(Uint16 x, Uint16 y)
{
	s_mouse_x = x;
	s_mouse_y = y;
	if (amigagfx_warp_pointer(x, y)) s_swallow_move = 1;
}

SDLMod SDL_GetModState(void) { return s_mods; }
void   SDL_SetModState(SDLMod modstate) { s_mods = modstate; }

Uint8 *SDL_GetKeyState(int *numkeys)
{
	/* OpenXcom never reads this, but SDL callers expect a valid array
	 * rather than NULL, so give it one that is simply always released. */
	static Uint8 keys[SDLK_LAST];
	if (numkeys != NULL) *numkeys = SDLK_LAST;
	return keys;
}

char *SDL_GetKeyName(SDLKey key)
{
	static char name[16];
	unsigned i;

	if (key >= SDLK_a && key <= SDLK_z) { name[0] = (char)key; name[1] = '\0'; return name; }
	if (key >= SDLK_0 && key <= SDLK_9) { name[0] = (char)key; name[1] = '\0'; return name; }

	for (i = 0; i < sizeof(s_keys) / sizeof(s_keys[0]); i++) {
		if (s_keys[i].sym != (int)key) continue;
		if (s_keys[i].ascii != 0) { name[0] = s_keys[i].ascii; name[1] = '\0'; return name; }
		break;
	}
	/* snprintf, never sprintf: see PROGRESS.md - sprintf is broken here. */
	snprintf(name, sizeof(name), "key %ld", (long)key);
	return name;
}

int SDL_EnableKeyRepeat(int delay, int interval)
{
	/* Intuition repeats keys for us, at the rate the player set in Prefs. */
	(void)delay; (void)interval;
	return 0;
}

int SDL_EnableUNICODE(int enable)
{
	int was = s_unicode_on;
	if (enable >= 0) s_unicode_on = enable;
	return was;
}

Uint8 SDL_GetAppState(void)
{
	return SDL_APPACTIVE | SDL_APPINPUTFOCUS | SDL_APPMOUSEFOCUS;
}

/* -------------------------------------------------------------- cursor -- */

/* The game draws its own pointer into the 8bpp buffer, so the only thing that
 * matters here is that Intuition's own pointer stops being drawn on top of
 * it. SDL_CreateCursor is called exactly to build a 1x1 invisible cursor;
 * we honour the intent rather than the bitmap. */

static SDL_Cursor s_cursor;
static int        s_cursor_shown = 1;

SDL_Cursor *SDL_CreateCursor(Uint8 *data, Uint8 *mask, int w, int h, int hot_x, int hot_y)
{
	(void)data; (void)mask;
	s_cursor.area.w = (Uint16)w;
	s_cursor.area.h = (Uint16)h;
	s_cursor.hot_x  = (Sint16)hot_x;
	s_cursor.hot_y  = (Sint16)hot_y;
	return &s_cursor;
}

void SDL_SetCursor(SDL_Cursor *cursor)
{
	(void)cursor;
	/* A 1x1 cursor is OpenXcom hiding the system pointer. */
	amigagfx_set_hide_system_pointer(1);
}

SDL_Cursor *SDL_GetCursor(void) { return &s_cursor; }

void SDL_FreeCursor(SDL_Cursor *cursor) { (void)cursor; }

int SDL_ShowCursor(int toggle)
{
	int was = s_cursor_shown;
	if (toggle >= 0) {
		s_cursor_shown = toggle;
		amigagfx_set_hide_system_pointer(!toggle);
	}
	return was;
}

/* ------------------------------------------------------ window manager -- */

static char s_caption[128] = "OpenXcom";

void SDL_WM_SetCaption(const char *title, const char *icon)
{
	(void)icon;
	if (title != NULL) {
		strncpy(s_caption, title, sizeof(s_caption) - 1);
		s_caption[sizeof(s_caption) - 1] = '\0';
		/* The screen title bar (wb_bar option) shows the game's own name -
		 * OpenXcom calls this before the display opens, so the title is
		 * already right when the bar first appears. */
		amigagfx_set_screen_title(s_caption);
	}
}

void SDL_WM_GetCaption(char **title, char **icon)
{
	if (title != NULL) *title = s_caption;
	if (icon != NULL)  *icon  = s_caption;
}

void SDL_WM_SetIcon(SDL_Surface *icon, Uint8 *mask)
{
	/* An Amiga program gets its icon from the .info file next to it. */
	(void)icon; (void)mask;
}

int SDL_WM_IconifyWindow(void) { return 0; }

SDL_GrabMode SDL_WM_GrabInput(SDL_GrabMode mode)
{
	(void)mode;
	return SDL_GRAB_OFF;
}

int SDL_GetWMInfo(SDL_SysWMinfo *info)
{
	(void)info;
	return 0;   /* no window-system handle to hand out */
}
