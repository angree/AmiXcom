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
	/* Delay() counts in ticks of 1/50 s. Anything under a tick would round
	 * to zero and busy-wait the caller, so it becomes one tick: on a machine
	 * this slow, giving the rest of the system a moment is never the wrong
	 * answer. */
	unsigned long ticks = ms / 20;
	if (ticks == 0) ticks = 1;
	Delay(ticks);
}
