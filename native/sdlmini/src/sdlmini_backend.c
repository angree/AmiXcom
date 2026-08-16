/*
 * Which display the port opens, decided once at startup.
 *
 * Three binaries ship: one hard-wired to AGA, one to RTG, and one that asks.
 * They are the same code - only AMIGA_BACKEND_DEFAULT differs - so a bug fixed
 * in one is fixed in all three, and any of them can still be pointed at the
 * other display with a command-line switch.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "sdlmini.h"
#include "amiga_gfx.h"
#include "amiga_startup.h"

#ifndef AMIGA_BACKEND_DEFAULT
#define AMIGA_BACKEND_DEFAULT AMIGA_STARTUP_AGA
#endif

void amiga_select_backend(int argc, char **argv)
{
	int choice = AMIGA_BACKEND_DEFAULT;
	int i;

	/* First line of the port that runs. It is the marker that says main() was
	 * reached at all - which matters, because a 12 MB executable that dies
	 * during load looks identical from the host side to one that dies in its
	 * first function. */
	SDLmini_Log("backend: entered (main reached)");

	for (i = 1; i < argc; i++) {
		if (argv[i] == NULL) continue;
		if (strcmp(argv[i], "-aga") == 0) choice = AMIGA_STARTUP_AGA;
		else if (strcmp(argv[i], "-rtg") == 0) choice = AMIGA_STARTUP_RTG;
		else if (strcmp(argv[i], "-ask") == 0) choice = AMIGA_STARTUP_QUIT - 1;  /* force the requester */
	}

	if (choice == AMIGA_STARTUP_QUIT || choice == AMIGA_STARTUP_QUIT - 1) {
		/* Ask. The RTG button is only offered when an 8-bit RTG mode big
		 * enough for the game actually exists, so an AGA-only machine is
		 * never given a choice it would only regret. */
		int rtg = amigagfx_rtg_has_mode(320, 200);
		choice = amigastartup_ask_backend(rtg);
		if (choice == AMIGA_STARTUP_QUIT) {
			SDLmini_Log("startup: cancelled at the display requester");
			exit(EXIT_SUCCESS);
		}
	}

	if (choice == AMIGA_STARTUP_RTG && !amigagfx_rtg_has_mode(320, 200)) {
		SDLmini_Log("startup: RTG asked for but no 8-bit RTG mode exists - using AGA");
		choice = AMIGA_STARTUP_AGA;
	}

	SDLmini_Log(choice == AMIGA_STARTUP_RTG ? "startup: display backend RTG"
	                                        : "startup: display backend AGA");
	SDLmini_SetBackend(choice);
}
