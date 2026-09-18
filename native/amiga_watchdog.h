#ifndef AMIGA_WATCHDOG_H
#define AMIGA_WATCHDOG_H
/* Hang reporter - see amiga_watchdog.c. The event pump bumps the beat once
 * per frame; start() after loading, stop() before the screen closes. */
#ifdef __cplusplus
extern "C" {
#endif
extern volatile unsigned long amiga_watchdog_beat;
void amiga_watchdog_start(void);
void amiga_watchdog_stop(void);
#ifdef __cplusplus
}
#endif
#endif
