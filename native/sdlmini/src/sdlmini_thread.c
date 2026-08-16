/*
 * SDLmini - threads and semaphores, serialised.
 *
 * Upstream OpenXcom creates exactly one thread, in Menu/StartState.cpp, to
 * load the game data while an animated console draws. Here that thread simply
 * runs to completion inside SDL_CreateThread: the loading screen then appears
 * as a single frame rather than an animation, and everything that follows sees
 * the same state it would have seen after joining the thread.
 *
 * Semaphores exist only to guard the FLC player audio callback against its own
 * mixer thread. With one thread there is nothing to guard, so they are
 * counters that never block - a wait that could block would deadlock instantly
 * and is therefore treated as a bug worth logging rather than a state to
 * emulate.
 */
#include <stdlib.h>

#include "SDL.h"
#include "SDL_thread.h"
#include "sdlmini.h"

struct SDL_Thread {
	int   ran;
	int   result;
};

SDL_Thread *SDL_CreateThread(int (*fn)(void *), void *data)
{
	SDL_Thread *t = (SDL_Thread *)calloc(1, sizeof(SDL_Thread));
	if (t == NULL) return NULL;

	SDLmini_Log("SDLmini: running a thread body inline (no threads in this port)");
	t->result = fn(data);
	t->ran    = 1;
	return t;
}

Uint32 SDL_ThreadID(void) { return 0; }

Uint32 SDL_GetThreadID(SDL_Thread *thread) { (void)thread; return 0; }

void SDL_WaitThread(SDL_Thread *thread, int *status)
{
	if (thread == NULL) return;
	if (status != NULL) *status = thread->result;
	free(thread);
}

void SDL_KillThread(SDL_Thread *thread)
{
	/* The body already finished; there is nothing to kill. */
	free(thread);
}

/* ----------------------------------------------------------- semaphores -- */

struct SDL_semaphore {
	Uint32 value;
};

SDL_sem *SDL_CreateSemaphore(Uint32 initial_value)
{
	SDL_sem *sem = (SDL_sem *)calloc(1, sizeof(SDL_sem));
	if (sem != NULL) sem->value = initial_value;
	return sem;
}

void SDL_DestroySemaphore(SDL_sem *sem) { free(sem); }

int SDL_SemWait(SDL_sem *sem)
{
	if (sem == NULL) return -1;
	if (sem->value == 0) {
		SDLmini_Log("SDLmini: SDL_SemWait on an empty semaphore - single-threaded, not waiting");
		return 0;
	}
	sem->value--;
	return 0;
}

int SDL_SemTryWait(SDL_sem *sem) { return SDL_SemWait(sem); }

int SDL_SemWaitTimeout(SDL_sem *sem, Uint32 timeout) { (void)timeout; return SDL_SemWait(sem); }

int SDL_SemPost(SDL_sem *sem)
{
	if (sem == NULL) return -1;
	sem->value++;
	return 0;
}

Uint32 SDL_SemValue(SDL_sem *sem) { return (sem != NULL) ? sem->value : 0; }

/* ---------------------------------------------------------------- mutex -- */

struct SDL_mutex {
	int held;
};

SDL_mutex *SDL_CreateMutex(void) { return (SDL_mutex *)calloc(1, sizeof(SDL_mutex)); }
void SDL_DestroyMutex(SDL_mutex *mutex) { free(mutex); }
int SDL_mutexP(SDL_mutex *mutex) { if (mutex != NULL) mutex->held = 1; return 0; }
int SDL_mutexV(SDL_mutex *mutex) { if (mutex != NULL) mutex->held = 0; return 0; }
