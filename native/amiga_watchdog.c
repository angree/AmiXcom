/*
 * amiga_watchdog.c - when the game stops, write down where it stopped.
 *
 * A Guru is cheap: amiga_trap.c logs the PC and the stack. A HANG is not -
 * the machine sits there with no requester, no log line, sometimes no CPU
 * load (a WaitIO that is never answered: the 0.9.6 music freeze), and all the
 * player can report is "it froze". That is what happened on 2026-09-17: the
 * game stopped at 00:06:54, the log simply ended, and nothing on the host or
 * in the guest said where.
 *
 * So: a small DOS process, started when loading has finished, that wakes once
 * a second and looks at a counter the game's event pump increments every
 * frame. When the counter has not moved for WD_STALL seconds it freezes the
 * scheduler for the length of a memcpy, copies the game task's state and the
 * top of its stack, and appends a report to PROGDIR:hang.log - in the same
 * shape as a CPU TRAP report, so winuae/harness/trapmap.py turns the stack
 * into function names. When the counter moves again it appends "resumed after
 * N s": a long save or a battle generation is a stall, not a hang, and the log
 * says which one it was.
 *
 * Reading a task that is not running is safe: on a single CPU the game task
 * is switched out while this one runs, tc_SPReg is where exec left its stack
 * (the saved PC is among the first longwords), and Forbid() keeps it from
 * moving under us. Nothing here touches stdio - libnix's is not shared
 * between processes - only dos.library, and never inside the Forbid.
 */
#include <exec/tasks.h>
#include <exec/execbase.h>
#include <dos/dos.h>
#include <dos/dosextens.h>
#include <dos/dostags.h>
#include <proto/exec.h>
#include <proto/dos.h>
#include <string.h>

#include "amiga_watchdog.h"

#define WD_STALL     30          /* seconds without a frame = report   */
#define WD_LONGS   1024          /* 4 KB of stack                      */

extern struct ExecBase *SysBase;
extern void amiga_trap_land(void);   /* amiga_trap.c: the textbase anchor */

volatile unsigned long amiga_watchdog_beat = 0;

static struct Task *s_game = NULL;
static volatile int s_quit = 0;
static volatile int s_running = 0;
static int s_started = 0;
static int s_reports = 0;

/* snapshot, taken under Forbid() */
static ULONG s_stack[WD_LONGS];
static ULONG s_nlongs, s_sp, s_lower, s_upper;
static ULONG s_state, s_sigwait, s_sigrecvd;
static LONG  s_idnest, s_tdnest;

static const char s_hex[] = "0123456789abcdef";

static char *put_hex(char *p, ULONG v)
{
	int i;
	for (i = 7; i >= 0; i--) *p++ = s_hex[(v >> (i * 4)) & 15];
	return p;
}

static char *put_str(char *p, const char *s)
{
	while (*s) *p++ = *s++;
	return p;
}

static char *put_dec(char *p, ULONG v)
{
	char t[12];
	int n = 0;
	do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v && n < 11);
	while (n) *p++ = t[--n];
	return p;
}

static void wd_write(const char *text, LONG len)
{
	BPTR fh;
	if (s_reports == 0) {
		fh = Open((CONST_STRPTR)"hang.log", MODE_NEWFILE);
	} else {
		fh = Open((CONST_STRPTR)"hang.log", MODE_READWRITE);
		if (fh) Seek(fh, 0, OFFSET_END);
	}
	if (!fh) return;
	Write(fh, (APTR)text, len);
	Close(fh);                    /* closed every time: the machine may be reset next */
	s_reports++;
}

static void snapshot(void)
{
	ULONG n;
	Forbid();
	s_sp      = (ULONG)s_game->tc_SPReg;
	s_lower   = (ULONG)s_game->tc_SPLower;
	s_upper   = (ULONG)s_game->tc_SPUpper;
	s_state   = (ULONG)s_game->tc_State;
	s_sigwait = (ULONG)s_game->tc_SigWait;
	s_sigrecvd = (ULONG)s_game->tc_SigRecvd;
	s_idnest  = (LONG)s_game->tc_IDNestCnt;
	s_tdnest  = (LONG)s_game->tc_TDNestCnt;
	n = 0;
	if ((s_sp & 1) == 0 && s_sp >= s_lower && s_sp < s_upper) {
		n = (s_upper - s_sp) / 4;
		if (n > WD_LONGS) n = WD_LONGS;
		memcpy(s_stack, (APTR)s_sp, n * 4);
	}
	s_nlongs = n;
	Permit();
}

static void report_hang(ULONG seconds, ULONG beat)
{
	static char buf[WD_LONGS * 9 + WD_LONGS / 8 * 12 + 1024];
	char *p = buf;
	ULONG i;

	snapshot();
	/* same shape as amiga_trap_describe(), so trapmap.py reads it */
	p = put_str(p, "\nHANG ");
	p = put_dec(p, seconds);
	p = put_str(p, " s without a frame (beat ");
	p = put_dec(p, beat);
	p = put_str(p, ") at PC 0x00000000 - PC is in the stack below\n");
	p = put_str(p, "  task state ");
	p = put_dec(p, s_state);
	p = put_str(p, s_state == TS_WAIT ? " (WAITING)" : s_state == TS_READY ? " (READY: busy)" : "");
	p = put_str(p, " sigwait 0x");
	p = put_hex(p, s_sigwait);
	p = put_str(p, " sigrecvd 0x");
	p = put_hex(p, s_sigrecvd);
	p = put_str(p, " idnest ");
	p = put_dec(p, (ULONG)(s_idnest + 1));
	p = put_str(p, " tdnest ");
	p = put_dec(p, (ULONG)(s_tdnest + 1));
	p = put_str(p, "\n  a0-a7: 00000000 00000000 00000000 00000000 00000000 00000000 00000000 ");
	p = put_hex(p, s_sp);
	p = put_str(p, "\n  stack 0x");
	p = put_hex(p, s_lower);
	p = put_str(p, "-0x");
	p = put_hex(p, s_upper);
	p = put_str(p, ", ");
	p = put_dec(p, s_nlongs);
	p = put_str(p, " longwords copied\n  textbase: amiga_trap_land is at 0x");
	p = put_hex(p, (ULONG)(APTR)amiga_trap_land);
	p = put_str(p, " (nm it to map the PC)\n");
	for (i = 0; i < s_nlongs; i++) {
		if ((i & 7) == 0) {
			p = put_str(p, i ? "\n  usp+" : "  usp+");
			*p++ = s_hex[(i * 4 >> 8) & 15];
			*p++ = s_hex[(i * 4 >> 4) & 15];
			*p++ = s_hex[(i * 4) & 15];
			*p++ = ':';
		}
		*p++ = ' ';
		p = put_hex(p, s_stack[i]);
	}
	p = put_str(p, "\n\n");
	wd_write(buf, (LONG)(p - buf));
}

static void report_resume(ULONG seconds)
{
	char buf[64];
	char *p = buf;
	p = put_str(p, "resumed after ");
	p = put_dec(p, seconds);
	p = put_str(p, " s\n");
	wd_write(buf, (LONG)(p - buf));
}

static void wd_main(void)
{
	ULONG last = amiga_watchdog_beat;
	ULONG still = 0;
	int reported = 0;

	s_running = 1;
	while (!s_quit) {
		Delay(50);
		if (amiga_watchdog_beat != last) {
			if (reported) report_resume(still);
			last = amiga_watchdog_beat;
			still = 0;
			reported = 0;
			continue;
		}
		still++;
		if (still == WD_STALL && !reported) {
			report_hang(still, last);
			reported = 1;
		}
	}
	Forbid();              /* stay alive until the process is torn down */
	s_running = 0;
}

void amiga_watchdog_start(void)
{
	struct Process *me;
	BPTR dir;

	if (s_started) return;
	s_started = 1;
	s_game = FindTask(NULL);
	me = (struct Process *)s_game;
	dir = (me->pr_Task.tc_Node.ln_Type == NT_PROCESS) ? GetProgramDir() : 0;
	dir = dir ? DupLock(dir) : 0;
	if (!CreateNewProcTags(NP_Entry, (ULONG)wd_main,
	                       NP_Name, (ULONG)"AmiXcom watchdog",
	                       NP_Priority, 1UL,
	                       NP_StackSize, 8192UL,
	                       NP_CurrentDir, (ULONG)dir,
	                       NP_Output, 0UL, NP_Input, 0UL,
	                       TAG_END)) {
		if (dir) UnLock(dir);
		s_started = 0;
	}
}

void amiga_watchdog_stop(void)
{
	int i;
	if (!s_started) return;
	s_quit = 1;
	for (i = 0; i < 40 && s_running; i++) Delay(5);   /* at most 4 s: one Delay(50) + margin */
	s_started = 0;
}
