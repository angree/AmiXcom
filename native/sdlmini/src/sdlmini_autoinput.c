/*
 * SDLmini - in-guest test driver.
 *
 * WHY: driving the game with synthetic mouse input on the HOST (mouse_event,
 * SetCursorPos) is not safe: WinUAE drops the mouse trap silently and the
 * clicks then land on whatever the user has on screen. So the test harness
 * never touches the host's input devices. Instead it writes a small script
 * to Work:autoinput.txt (the shared folder), and this module - inside the
 * emulated machine - reads it and feeds the events into SDLmini's own event
 * queue. The game cannot tell them from real input; the user's machine is
 * never touched.
 *
 * File format, one command per line, '#' comments:
 *     move X Y            pointer to (X,Y) in game (320x200) coordinates
 *     click X Y           move there, left button down, up 120 ms later
 *     rclick X Y          same with the right button
 *     key NAME            press+release; NAME is an SDLK number, a single
 *                         character, or one of: escape return space tab
 *                         up down left right f1..f12 backspace
 *     wait MS             pause before the next command
 *     quit                exit the game cleanly (SDL_QUIT)
 * The file is polled about twice a second and DELETED once fully consumed,
 * so the host knows it was taken; the host writes the next batch afterwards.
 * Every command is logged as "autoinput: ...".
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#include "SDL.h"
#include "sdlmini.h"

#define AUTOINPUT_FILE "PROGDIR:autoinput.txt"
#define MAX_SCRIPT     8192

static char   s_script[MAX_SCRIPT];
static char  *s_cursor;                 /* next line to run, NULL = idle    */
static Uint32 s_next_time;              /* SDL ticks before the next command */
static Uint32 s_last_poll;
static int    s_pending_release;        /* button to release at s_next_time */
static int    s_pending_key;            /* key to release at s_next_time    */

static int key_by_name(const char *name)
{
	static const struct { const char *n; int sym; } names[] = {
		{ "escape", SDLK_ESCAPE }, { "esc", SDLK_ESCAPE }, { "return", SDLK_RETURN },
		{ "enter", SDLK_RETURN }, { "space", SDLK_SPACE }, { "tab", SDLK_TAB },
		{ "up", SDLK_UP }, { "down", SDLK_DOWN }, { "left", SDLK_LEFT }, { "right", SDLK_RIGHT },
		{ "backspace", SDLK_BACKSPACE }, { "delete", SDLK_DELETE },
		{ "f1", SDLK_F1 }, { "f2", SDLK_F2 }, { "f3", SDLK_F3 }, { "f4", SDLK_F4 },
		{ "f5", SDLK_F5 }, { "f6", SDLK_F6 }, { "f7", SDLK_F7 }, { "f8", SDLK_F8 },
		{ "f9", SDLK_F9 }, { "f10", SDLK_F10 }, { "f11", SDLK_F11 }, { "f12", SDLK_F12 },
	};
	size_t i;
	for (i = 0; i < sizeof(names) / sizeof(names[0]); i++)
		if (strcmp(names[i].n, name) == 0) return names[i].sym;
	if (strlen(name) == 1) return (unsigned char)tolower((unsigned char)name[0]);
	if (isdigit((unsigned char)name[0])) return atoi(name);
	return 0;
}

static void load_script(void)
{
	FILE *f = fopen(AUTOINPUT_FILE, "r");
	size_t n;
	if (f == NULL) return;
	n = fread(s_script, 1, MAX_SCRIPT - 1, f);
	fclose(f);
	s_script[n] = 0;
	if (n == 0) { remove(AUTOINPUT_FILE); return; }
	s_cursor = s_script;
	s_next_time = SDL_GetTicks();
	SDLmini_Log("autoinput: script loaded");
}

static void finish_script(void)
{
	s_cursor = NULL;
	remove(AUTOINPUT_FILE);
	SDLmini_Log("autoinput: script done, file removed");
}

/* Run one command; returns the delay in ms before the next one. */
static Uint32 run_line(char *line)
{
	char cmd[32], arg1[32], arg2[32];
	int x = 0, y = 0, n;
	char lb[128];

	while (*line == ' ' || *line == '\t') line++;
	if (*line == 0 || *line == '#') return 0;

	n = sscanf(line, "%31s %31s %31s", cmd, arg1, arg2);
	if (n < 1) return 0;
	snprintf(lb, sizeof(lb), "autoinput: %s", line);
	SDLmini_Log(lb);

	if (strcmp(cmd, "wait") == 0 && n >= 2)
		return (Uint32)atoi(arg1);

	if ((strcmp(cmd, "move") == 0 || strcmp(cmd, "click") == 0 ||
	     strcmp(cmd, "rclick") == 0) && n >= 3) {
		x = atoi(arg1); y = atoi(arg2);
		SDLmini_InjectMouseMove(x, y);
		if (cmd[0] == 'm') return 50;
		{
			int button = (cmd[0] == 'r') ? SDL_BUTTON_RIGHT : SDL_BUTTON_LEFT;
			SDLmini_InjectMouseButton(button, 1);
			s_pending_release = button;
			return 120;
		}
	}
	if (strcmp(cmd, "key") == 0 && n >= 2) {
		int sym = key_by_name(arg1);
		if (sym == 0) { SDLmini_Log("autoinput: unknown key name"); return 0; }
		SDLmini_InjectKey(sym, 1);
		s_pending_key = sym;
		return 80;
	}
	if (strcmp(cmd, "quit") == 0) {
		SDL_Event ev;
		memset(&ev, 0, sizeof(ev));
		ev.type = SDL_QUIT;
		SDL_PushEvent(&ev);
		return 0;
	}
	SDLmini_Log("autoinput: unknown command");
	return 0;
}

/* Opt-in, and off unless the file says so.
 *
 * This layer injects mouse moves and clicks into the game's own event queue.
 * It exists for agent-driven test runs, and it has no business running while
 * somebody is playing: a script left behind (or still held in memory from an
 * earlier load - the file is read in one go and deleted immediately) makes the
 * cursor move on its own, which reads exactly like a bug in the game. It now
 * requires Work:autoinput.on to exist; without that file the poll never even
 * looks for a script. Checked once, at the first poll. */
static int autoinput_enabled(void)
{
	static int s_enabled = -1;
	if (s_enabled < 0) {
		FILE *f = fopen("PROGDIR:autoinput.on", "r");
		s_enabled = (f != NULL);
		if (f != NULL) fclose(f);
		SDLmini_Log(s_enabled ? "autoinput: ENABLED (Work:autoinput.on present)"
		                      : "autoinput: disabled (no Work:autoinput.on)");
	}
	return s_enabled;
}

void SDLmini_AutoinputPoll(void)
{
	Uint32 now = SDL_GetTicks();

	if (!autoinput_enabled()) return;

	if (s_cursor == NULL) {
		if (now - s_last_poll < 500) return;
		s_last_poll = now;
		load_script();
		if (s_cursor == NULL) return;
	}
	if ((Sint32)(now - s_next_time) < 0) return;

	/* deferred releases first, so a click is down->(120 ms)->up */
	if (s_pending_release) {
		SDLmini_InjectMouseButton(s_pending_release, 0);
		s_pending_release = 0;
		s_next_time = now + 150;
		return;
	}
	if (s_pending_key) {
		SDLmini_InjectKey(s_pending_key, 0);
		s_pending_key = 0;
		s_next_time = now + 100;
		return;
	}

	{
		char *line = s_cursor;
		char *nl = strchr(line, '\n');
		Uint32 delay;
		if (nl) { *nl = 0; s_cursor = nl + 1; } else { s_cursor = line + strlen(line); }
		if (nl && nl > line && nl[-1] == '\r') nl[-1] = 0;
		delay = run_line(line);
		s_next_time = now + (delay ? delay : 30);
		if (*s_cursor == 0 && !s_pending_release && !s_pending_key)
			finish_script();
		else if (*s_cursor == 0)
			; /* release still pending; finish on the next poll */
	}
}
