/*
 * SDLmini - the one file allowed to include Amiga headers besides
 * amiga_gfx.c, and it includes exactly one of them.
 *
 * It is separate because dos.library headers and SDL headers must never meet:
 * the Amiga inline headers define function-style macros (Insert, Remove,
 * Allocate) that collide with ordinary identifiers in C++ game code. Keeping
 * this in its own translation unit costs nothing and removes the whole class
 * of problem - the same rule the openttd_amiga_68k port follows.
 */
#include <proto/dos.h>

void SDLmini_Sleep(unsigned long ms)
{
	/* Delay() counts in ticks of 1/50 s. OpenXcom ends EVERY frame with
	 * SDL_Delay(1) ("save CPU") - rounding that up to a tick put a forced
	 * 20 ms nap into each frame, a third of the whole frame time on the
	 * target machine (measured 2026-08-17: 60 ms frames, ~20 of them here).
	 * Sub-tick delays are therefore a no-op: Exec is preemptive, so system
	 * tasks run anyway, and the game loop's own FPS limiter still paces
	 * rendering. Real waits (pause menus ask for 100 ms) keep sleeping. */
	unsigned long ticks = ms / 20;
	if (ticks == 0) {
		if (ms > 2) ticks = 1;      /* 3..19 ms: closest honest wait */
		else return;                /* the per-frame "yield": free on Amiga */
	}
	Delay(ticks);
}
