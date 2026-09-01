/*
 * SDLmini - core: init, error string, ticks, delay, environment.
 *
 * Part of the AmigaOS 68k OpenXcom port. See include/SDL_config.h for what
 * SDLmini is and why it exists.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "sdlmini.h"
#include "amiga_gfx.h"

static Uint32 s_initialised;
static char   s_error[256];

/* ---------------------------------------------------------------- errors -- */

void SDL_SetError(const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(s_error, sizeof(s_error), fmt, ap);
	va_end(ap);
	s_error[sizeof(s_error) - 1] = '\0';
	SDLmini_Log(s_error);
}

char *SDL_GetError(void)
{
	return s_error;
}

void SDL_ClearError(void)
{
	s_error[0] = '\0';
}

/* SDL's own internal error hook; some headers reference it. */
void SDL_Error(SDL_errorcode code)
{
	SDL_SetError("SDL error %d", (int)code);
}

/* ------------------------------------------------------------------ log -- */

/* One place for everything SDLmini wants to say.
 *
 * It goes to two places on purpose. amiga_gfx.c owns the game's log, but that
 * one only becomes readable once a screen exists; a crash before then leaves
 * nothing at all to read, and on this machine an early crash does not even
 * produce a Guru - the emulated CPU double-faults and WinUAE simply stops with
 * HALT1 and a black screen. So every line is also appended to
 * PROGDIR:sdlmini.log, which is on the host side of the shared folder and
 * survives whatever happens next.
 *
 * The FILE is opened once and only flushed afterwards, never reopened: the
 * openttd port found that ~60-70 fopen/append/fclose cycles are enough to
 * crash a libnix program, and a log that kills the thing it is documenting is
 * worse than no log. */
void SDLmini_Log(const char *msg)
{
	static FILE *s_file;
	static int   s_tried;

	if (!s_tried) {
		s_tried = 1;
		s_file = fopen("PROGDIR:sdlmini.log", "w");
	}
	/* Every line is stamped with seconds since the first one. Without that,
	 * "it takes five minutes to start" cannot be turned into "which of these
	 * eleven steps takes the five minutes", and that question has come up
	 * once per debugging session. */
	if (s_file != NULL) {
		fprintf(s_file, "[%6ld.%02ld] %s\n",
		        (long)(SDL_GetTicks() / 1000UL),
		        (long)((SDL_GetTicks() / 10UL) % 100UL), msg);
		fflush(s_file);
	}
	amigagfx_log(msg);
}

/* ------------------------------------------------------------------ init -- */

int SDL_Init(Uint32 flags)
{
	return SDL_InitSubSystem(flags);
}

int SDL_InitSubSystem(Uint32 flags)
{
	if ((flags & SDL_INIT_VIDEO) && !(s_initialised & SDL_INIT_VIDEO)) {
		SDLmini_VideoInit();
	}
	if ((flags & SDL_INIT_AUDIO) && !(s_initialised & SDL_INIT_AUDIO)) {
		/* The mixer opens Paula lazily in Mix_OpenAudio; nothing to do here. */
	}
	s_initialised |= flags;
	return 0;
}

void SDL_QuitSubSystem(Uint32 flags)
{
	/* Audio first: Paula is holding channels and audio.device requests, and
	 * those are the ones the OS does not take back on its own. Closing the
	 * screen first would leave them allocated for the rest of the session. */
	if ((flags & SDL_INIT_AUDIO) && (s_initialised & SDL_INIT_AUDIO)) {
		extern void Mix_CloseAudio(void);
		Mix_CloseAudio();
	}
	if ((flags & SDL_INIT_VIDEO) && (s_initialised & SDL_INIT_VIDEO)) {
		SDLmini_VideoQuit();
	}
	s_initialised &= ~flags;
}

Uint32 SDL_WasInit(Uint32 flags)
{
	if (flags == 0) flags = SDL_INIT_EVERYTHING;
	return s_initialised & flags;
}

void SDL_Quit(void)
{
	SDL_QuitSubSystem(SDL_INIT_EVERYTHING);
	s_initialised = 0;
}

/* ----------------------------------------------------------------- time -- */

Uint32 SDL_GetTicks(void)
{
	{ extern void SDLmini_MusicPump(void); SDLmini_MusicPump(); }
	return (Uint32)amigagfx_millis();
}

void SDL_Delay(Uint32 ms)
{
	{ extern void SDLmini_MusicPump(void); SDLmini_MusicPump(); }
	SDLmini_Sleep(ms);
}

/* ------------------------------------------------------------ environment -- */

/* OpenXcom uses SDL_putenv only to place the window on the desktop, which
 * means nothing here. Accepting and ignoring it keeps Screen.cpp unpatched. */
int SDL_putenv(const char *variable)
{
	(void)variable;
	return 0;
}

/* --------------------------------------------------------------- version -- */

static SDL_version s_version = { 1, 2, 15 };

const SDL_version *SDL_Linked_Version(void)
{
	return &s_version;
}
