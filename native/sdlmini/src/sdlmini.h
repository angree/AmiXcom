/*
 * SDLmini - internal interface shared by the shim's own translation units.
 * Nothing outside native/sdlmini/src includes this.
 */
#ifndef SDLMINI_H
#define SDLMINI_H

#include "SDL.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Which amiga_gfx backend the next SDL_SetVideoMode should ask for, as an
 * AMIGAGFX_BACKEND_* value. The port's main() sets this from the command line
 * / config / the startup requester before SDL_Init; SDLmini never guesses. */
void SDLmini_SetBackend(int backend);
int  SDLmini_GetBackend(void);

/* Called from SDL_Init / SDL_Quit. */
void SDLmini_VideoInit(void);
void SDLmini_VideoQuit(void);

/* The video surface, or NULL before SDL_SetVideoMode. */
SDL_Surface *SDLmini_ScreenSurface(void);

/* Drain amiga_gfx's IDCMP queue into the SDL event queue. */
void SDLmini_PumpEvents(void);
/* in-guest test driver (sdlmini_autoinput.c) - see that file */
void SDLmini_InjectMouseMove(int x, int y);
void SDLmini_InjectMouseButton(int button, int down);
void SDLmini_InjectKey(int sym, int down);
void SDLmini_AutoinputPoll(void);

/* Mouse/modifier state, maintained by the event pump and read back by
 * SDL_GetMouseState / SDL_GetModState. */
void SDLmini_SetMousePos(int x, int y);

/* dos.library Delay(), in milliseconds. Lives in amiga_gfx.c's world so this
 * file stays free of Amiga headers. */
void SDLmini_Sleep(unsigned long ms);

/* One log line, routed through amiga_gfx.c's log file. */
void SDLmini_Log(const char *msg);
extern int SDLmini_diag_armed; /* TEMP diagnostic switch (sdlmini_video.c) */
extern unsigned long SDLmini_flips; /* frames rendered so far (sdlmini_video.c) */

#ifdef __cplusplus
}
#endif

#endif /* SDLMINI_H */
