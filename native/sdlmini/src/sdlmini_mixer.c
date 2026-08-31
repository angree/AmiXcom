/*
 * SDLmini - SDL_mixer API on four Paula channels.
 *
 * Deliberately primitive, for the reason the port exists at all: the CPU is
 * the scarce resource and X-COM is turn-based. There is no software mixing.
 * A sound is converted once, at load, into 8-bit signed mono in Chip RAM, and
 * from then on it is played by DMA with the CPU doing nothing.
 *
 * Channel model (same as the openttd_amiga_68k port):
 *   - 4 hardware channels. With music streaming, channels 2 and 3 belong to
 *     the music and effects use 0 and 1; with music off, effects use all four.
 *   - When every usable channel is busy, the oldest one is stolen rather than
 *     dropping the new sound - a game with two effect channels that silently
 *     swallows sounds feels broken, and X-COM leans on its audio cues.
 *
 * OpenXcom asks for 16 mixer channels and reserves four of them; those numbers
 * are remapped here onto the hardware, so channel numbers coming from the game
 * are treated as hints, not as hardware indices.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "SDL_mixer.h"
#include "sdlmini.h"
#include "amiga_audio.h"

#include <exec/memory.h>
#include <proto/exec.h>

/* Paula's clock follows the display standard: 3546895 Hz on PAL,
 * 3579545 on NTSC. It used to be PAL only, which played every sound
 * about 0.9% sharp on an NTSC machine. Read once, on first use. */
unsigned long amigagfx_paula_clock(void);
static long paula_clock(void)
{
	static long c = 0;
	if (c == 0) c = (long)amigagfx_paula_clock();
	return c;
}
#define PAL_CLOCK paula_clock()

static int  s_open;
static int  s_rate = 22050;
static char s_error[128];
static int  s_master_volume = MIX_MAX_VOLUME;   /* Mix_Volume(-1, v) */
static int  s_chan_volume[AMIGA_AUDIO_CHANNELS];

/* Which game-side channel last claimed each hardware channel, and in what
 * order, so the oldest can be stolen. */
static unsigned long s_started[AMIGA_AUDIO_CHANNELS];
static unsigned long s_serial;

/* One Chip RAM staging buffer per hardware channel. Sounds themselves live in
 * Fast RAM (see Mix_LoadWAV_RW) and are copied in here to be played, because
 * Paula reads Chip RAM and there is not enough of it to hold X-COM's whole
 * sound set. 32 KB is a second and a half at 22 kHz - longer than any effect
 * in the game; anything longer is truncated rather than refused. */
#define CHIP_STAGE_BYTES 32768
static Uint8 *s_stage[AMIGA_AUDIO_CHANNELS];
static int    s_stage_warned;

static void set_error(const char *msg)
{
	strncpy(s_error, msg, sizeof(s_error) - 1);
	s_error[sizeof(s_error) - 1] = '\0';
	SDLmini_Log(msg);
}

/* RAM is the top unresolved risk of this port, so every allocation failure
 * reports how much was asked for and what was left. A bare "out of memory"
 * says nothing about whether the machine is 1 KB or 8 MB short. */
static void sdlmini_log_mem(const char *what, unsigned long want)
{
	char buf[144];
	snprintf(buf, sizeof(buf), "SDLmini: %s failed, wanted %lu B; free fast %lu KB chip %lu KB largest %lu KB",
	        what, want,
	        (unsigned long)(AvailMem(MEMF_FAST) >> 10),
	        (unsigned long)(AvailMem(MEMF_CHIP) >> 10),
	        (unsigned long)(AvailMem(MEMF_ANY | MEMF_LARGEST) >> 10));
	SDLmini_Log(buf);
}

const char *Mix_GetError(void) { return s_error; }

/* --------------------------------------------------------------- device -- */

int Mix_OpenAudio(int frequency, Uint16 format, int channels, int chunksize)
{
	int i;
	(void)format; (void)channels; (void)chunksize;

	if (s_open) return 0;
	if (!AmigaAudio_Open()) {
		set_error("SDLmini: audio.device unavailable - running silent");
		return -1;
	}
	s_rate = (frequency > 0) ? frequency : 22050;
	/* Paula cannot go above about 28 kHz without aliasing artefacts on the
	 * period register; anything the game asks for above that is clamped. */
	if (s_rate > 28000) s_rate = 28000;

	for (i = 0; i < AMIGA_AUDIO_CHANNELS; i++) {
		s_chan_volume[i] = MIX_MAX_VOLUME;
		s_stage[i] = (Uint8 *)AmigaAudio_AllocSample(CHIP_STAGE_BYTES);
		if (s_stage[i] == NULL) set_error("SDLmini: no Chip RAM for a playback buffer");
	}
	s_open = 1;
	return 0;
}

void Mix_CloseAudio(void)
{
	int i;
	if (!s_open) return;
	AmigaAudio_Close();
	for (i = 0; i < AMIGA_AUDIO_CHANNELS; i++) {
		AmigaAudio_FreeSample(s_stage[i]);
		s_stage[i] = NULL;
	}
	s_open = 0;
}

int Mix_AllocateChannels(int numchans)
{
	(void)numchans;
	return AMIGA_AUDIO_CHANNELS;
}

int Mix_ReserveChannels(int num) { (void)num; return AMIGA_AUDIO_CHANNELS; }

int Mix_GroupChannels(int from, int to, int tag)
{
	(void)from; (void)to; (void)tag;
	return 0;
}

int Mix_GroupAvailable(int tag)
{
	int i;
	(void)tag;
	for (i = 0; i < AMIGA_AUDIO_CHANNELS; i++) {
		if (AmigaAudio_ChannelIdle(i)) return i;
	}
	return -1;
}

/* ---------------------------------------------------------------- loads -- */

/* Minimal RIFF/WAVE reader: PCM only, 8 or 16 bit, mono or stereo, any rate.
 * Everything is converted to the one format Paula plays - 8-bit signed mono -
 * at load time, so playback costs nothing. Resampling is nearest-neighbour on
 * purpose: X-COM effects are short, already low quality, and a proper
 * resampler would cost more than the whole audio subsystem is worth here. */
static int wav_to_paula(const Uint8 *data, Uint32 size, Uint8 **out, Uint32 *outlen)
{
	Uint32 pos = 12;
	int channels = 1, bits = 8;
	Uint32 rate = 11025;
	const Uint8 *pcm = NULL;
	Uint32 pcmlen = 0;

	if (size < 44 || memcmp(data, "RIFF", 4) != 0 || memcmp(data + 8, "WAVE", 4) != 0) {
		char msg[128];
		/* %lu / %02lx, never %u / %02x: printf on this libc pulls 16 bits
		 * for %d and %x (the AmigaOS %ld convention), so a plain %x eats half
		 * an argument and every value after it is garbage. */
		snprintf(msg, sizeof(msg), "SDLmini: not a RIFF/WAVE sound (%lu B, starts %02lx %02lx %02lx %02lx %02lx %02lx %02lx %02lx)",
		        (unsigned long)size,
		        (unsigned long)(size > 0 ? data[0] : 0), (unsigned long)(size > 1 ? data[1] : 0),
		        (unsigned long)(size > 2 ? data[2] : 0), (unsigned long)(size > 3 ? data[3] : 0),
		        (unsigned long)(size > 4 ? data[4] : 0), (unsigned long)(size > 5 ? data[5] : 0),
		        (unsigned long)(size > 6 ? data[6] : 0), (unsigned long)(size > 7 ? data[7] : 0));
		set_error(msg);
		return 0;
	}

	while (pos + 8 <= size) {
		Uint32 id   = (Uint32)data[pos] | ((Uint32)data[pos+1] << 8) | ((Uint32)data[pos+2] << 16) | ((Uint32)data[pos+3] << 24);
		Uint32 clen = (Uint32)data[pos+4] | ((Uint32)data[pos+5] << 8) | ((Uint32)data[pos+6] << 16) | ((Uint32)data[pos+7] << 24);
		const Uint8 *body = data + pos + 8;

		if (id == 0x20746d66UL) {              /* "fmt " */
			channels = (int)(body[2] | (body[3] << 8));
			rate     = (Uint32)body[4] | ((Uint32)body[5] << 8) | ((Uint32)body[6] << 16) | ((Uint32)body[7] << 24);
			bits     = (int)(body[14] | (body[15] << 8));
		} else if (id == 0x61746164UL) {       /* "data" */
			pcm    = body;
			pcmlen = clen;
			if (pos + 8 + clen > size) pcmlen = size - pos - 8;
			break;
		}
		pos += 8 + clen + (clen & 1);
	}

	if (pcm == NULL || pcmlen == 0) {
		set_error("SDLmini: WAVE has no data chunk");
		return 0;
	}
	if (bits != 8 && bits != 16) {
		set_error("SDLmini: only 8 and 16 bit PCM sounds are supported");
		return 0;
	}

	{
		Uint32 frameBytes = (Uint32)(bits / 8) * (Uint32)channels;
		Uint32 frames     = pcmlen / frameBytes;
		Uint32 outFrames;
		Uint32 i;
		Uint8 *dst;

		/* Nearest-neighbour rate conversion to the rate the device was
		 * opened at, so every sound shares one Paula period.
		 *
		 * Integer arithmetic throughout, in 64 bits: the target CPU is a
		 * plain 68020 with no FPU, and a double here would pull in the
		 * soft-float library for what is a ratio of two small integers. */
		outFrames = (Uint32)(((unsigned long long)frames * (unsigned long long)s_rate) / (unsigned long long)rate);
		if (outFrames < 2) outFrames = 2;
		if (outFrames & 1) outFrames++;         /* Paula plays word pairs */

		/* Decoded samples live in FAST RAM. X-COM loads its whole sound set
		 * at startup and there is nowhere near enough Chip RAM for that -
		 * the 2 MB of an A4000 runs out long before the effects do. Paula
		 * can only read Chip RAM, so a sound is copied into a small
		 * per-channel Chip buffer at the moment it is played. */
		dst = (Uint8 *)malloc(outFrames);
		if (dst == NULL) {
			set_error("SDLmini: out of memory for a sound");
			return 0;
		}

		for (i = 0; i < outFrames; i++) {
			Uint32 srcFrame = (Uint32)(((unsigned long long)i * (unsigned long long)frames) / (unsigned long long)outFrames);
			const Uint8 *f;
			int v;

			if (srcFrame >= frames) srcFrame = frames - 1;
			f = pcm + srcFrame * frameBytes;

			if (bits == 8) {
				v = (int)f[0] - 128;                       /* unsigned -> signed */
				if (channels > 1) v = (v + ((int)f[1] - 128)) / 2;
			} else {
				int l = (int)(Sint16)(f[0] | (f[1] << 8));
				if (channels > 1) {
					int r = (int)(Sint16)(f[2] | (f[3] << 8));
					l = (l + r) / 2;
				}
				v = l >> 8;
			}
			if (v > 127) v = 127;
			if (v < -128) v = -128;
			dst[i] = (Uint8)(signed char)v;
		}

		*out    = dst;
		*outlen = outFrames;
	}
	return 1;
}

Mix_Chunk *Mix_LoadWAV_RW(SDL_RWops *src, int freesrc)
{
	Mix_Chunk *chunk;
	Uint8 *buf = NULL;
	int size;
	Uint8 *pcm = NULL;
	Uint32 pcmlen = 0;

	if (src == NULL) return NULL;

	size = SDL_RWseek(src, 0, RW_SEEK_END);
	SDL_RWseek(src, 0, RW_SEEK_SET);
	if (size <= 0) {
		set_error("SDLmini: empty sound");
		if (freesrc) SDL_RWclose(src);
		return NULL;
	}
	buf = (Uint8 *)malloc((size_t)size);
	if (buf == NULL) {
		sdlmini_log_mem("sound read", (unsigned long)size);
		set_error("SDLmini: out of memory reading a sound");
		if (freesrc) SDL_RWclose(src);
		return NULL;
	}
	SDL_RWread(src, buf, 1, size);
	if (freesrc) SDL_RWclose(src);

	if (!s_open || !wav_to_paula(buf, (Uint32)size, &pcm, &pcmlen)) {
		free(buf);
		return NULL;
	}
	free(buf);

	chunk = (Mix_Chunk *)calloc(1, sizeof(Mix_Chunk));
	if (chunk == NULL) {
		free(pcm);
		sdlmini_log_mem("chunk alloc", (unsigned long)sizeof(Mix_Chunk));
		set_error("SDLmini: out of memory (chunk)");
		return NULL;
	}
	chunk->allocated = 1;
	chunk->abuf      = pcm;
	chunk->alen      = pcmlen;
	chunk->volume    = MIX_MAX_VOLUME;
	return chunk;
}

Mix_Chunk *Mix_LoadWAV(const char *file)
{
	SDL_RWops *rw = SDL_RWFromFile(file, "rb");
	if (rw == NULL) return NULL;
	return Mix_LoadWAV_RW(rw, 1);
}

void Mix_FreeChunk(Mix_Chunk *chunk)
{
	if (chunk == NULL) return;
	if (chunk->allocated) free(chunk->abuf);
	free(chunk);
}

/* -------------------------------------------------------------- playing -- */

/* Effects avoid the music channels while music is streaming. */
static int first_sfx_channel(void) { return AmigaAudio_MusicActive() ? 0 : 0; }
static int last_sfx_channel(void)  { return AmigaAudio_MusicActive() ? 1 : 3; }

static int pick_channel(void)
{
	int i, oldest = first_sfx_channel();
	unsigned long oldestAt = ~0UL;

	for (i = first_sfx_channel(); i <= last_sfx_channel(); i++) {
		if (AmigaAudio_ChannelIdle(i)) return i;
		if (s_started[i] < oldestAt) { oldestAt = s_started[i]; oldest = i; }
	}
	/* Everything is busy: steal the oldest. Paula stops on the next DMA
	 * word either way, so this is the "fast fade-out" the design calls for
	 * as far as a 4-channel chipset can provide one. */
	return oldest;
}

int Mix_PlayChannel(int channel, Mix_Chunk *chunk, int loops)
{
	int hw;
	int volume;
	int period;

	if (!s_open || chunk == NULL || chunk->abuf == NULL) return -1;
	(void)loops;   /* looping ambience is restarted by the game each turn */

	hw = (channel >= first_sfx_channel() && channel <= last_sfx_channel() && AmigaAudio_ChannelIdle(channel))
	     ? channel : pick_channel();

	volume = (s_chan_volume[hw] * s_master_volume) / MIX_MAX_VOLUME;
	volume = (volume * 64) / MIX_MAX_VOLUME;           /* Paula volume is 0..64 */
	if (volume > 64) volume = 64;
	if (volume < 0)  volume = 0;

	period = (int)(PAL_CLOCK / (long)s_rate);
	if (period < 124) period = 124;

	if (s_stage[hw] == NULL) return -1;
	{
		Uint32 len = chunk->alen;
		if (len > CHIP_STAGE_BYTES) {
			len = CHIP_STAGE_BYTES;
			if (!s_stage_warned) {
				s_stage_warned = 1;
				set_error("SDLmini: a sound was longer than the Chip staging buffer and was cut");
			}
		}
		if (len < 2) return -1;
		len &= ~1UL;                       /* Paula plays word pairs */
		memcpy(s_stage[hw], chunk->abuf, len);
		if (!AmigaAudio_Play(hw, s_stage[hw], len, period, volume)) return -1;
	}
	s_started[hw] = ++s_serial;
	return hw;
}

int Mix_PlayChannelTimed(int channel, Mix_Chunk *chunk, int loops, int ticks)
{
	(void)ticks;
	return Mix_PlayChannel(channel, chunk, loops);
}

int Mix_HaltChannel(int channel)
{
	/* audio.device stops a channel by starting nothing on it; the sounds
	 * here are short enough that letting them finish is both simpler and
	 * less jarring than an abrupt cut. */
	(void)channel;
	return 0;
}

int Mix_FadeOutChannel(int which, int ms)
{
	(void)ms;
	return Mix_HaltChannel(which);
}

int Mix_Playing(int channel)
{
	int i, n = 0;
	if (!s_open) return 0;
	if (channel < 0) {
		for (i = 0; i < AMIGA_AUDIO_CHANNELS; i++) if (!AmigaAudio_ChannelIdle(i)) n++;
		return n;
	}
	if (channel >= AMIGA_AUDIO_CHANNELS) return 0;
	return AmigaAudio_ChannelIdle(channel) ? 0 : 1;
}

int Mix_Volume(int channel, int volume)
{
	int was;
	if (channel < 0) {
		was = s_master_volume;
		if (volume >= 0) s_master_volume = (volume > MIX_MAX_VOLUME) ? MIX_MAX_VOLUME : volume;
		return was;
	}
	if (channel >= AMIGA_AUDIO_CHANNELS) return 0;
	was = s_chan_volume[channel];
	if (volume >= 0) s_chan_volume[channel] = (volume > MIX_MAX_VOLUME) ? MIX_MAX_VOLUME : volume;
	return was;
}

int Mix_SetPosition(int channel, Sint16 angle, Uint8 distance)
{
	/* Paula channels 0 and 3 are the left jack, 1 and 2 the right, so
	 * panning means choosing a channel - which happened at play time. There
	 * is nothing to change afterwards, and reporting failure would make the
	 * game log a warning per sound. */
	(void)channel; (void)angle; (void)distance;
	return 1;
}

/* ---------------------------------------------------------------- music -- */

/* Music is built out of ADPCM tracks streamed from disk (amiga_adpcm.c) in a
 * later stage of the port; the game is compiled with __NO_MUSIC for now, so
 * these exist only to satisfy the few unguarded references. */

struct _Mix_Music { int dummy; };

Mix_Music *Mix_LoadMUS(const char *file)      { (void)file; return NULL; }
Mix_Music *Mix_LoadMUS_RW(SDL_RWops *rw)      { (void)rw;   return NULL; }
void       Mix_FreeMusic(Mix_Music *music)    { (void)music; }
int        Mix_PlayMusic(Mix_Music *m, int l) { (void)m; (void)l; return -1; }
int        Mix_VolumeMusic(int volume)        { AmigaAudio_MusicSetVolume((volume * 64) / MIX_MAX_VOLUME); return volume; }
int        Mix_HaltMusic(void)                { AmigaAudio_MusicStop(); return 0; }
int        Mix_FadeOutMusic(int ms)           { (void)ms; return Mix_HaltMusic(); }
void       Mix_PauseMusic(void)               { }
void       Mix_ResumeMusic(void)              { }
int        Mix_PlayingMusic(void)             { return AmigaAudio_MusicActive(); }
Mix_MusicType Mix_GetMusicType(const Mix_Music *music) { (void)music; return MUS_NONE; }
void       Mix_HookMusic(void (*f)(void *, Uint8 *, int), void *arg) { (void)f; (void)arg; }
void       Mix_HookMusicFinished(void (*f)(void)) { (void)f; }

void SDLmini_MixerService(void)
{
	if (s_open) AmigaAudio_MusicService();
}

/* Same thing, but safe to call from the hot paths the game runs through
 * when it is NOT drawing: timing calls, the event poll, long yaml parses.
 * Throttled, because SDL_GetTicks alone is called thousands of times a
 * second and CheckIO is not free. The guard keeps it re-entrant-safe. */
void SDLmini_MusicPump(void)
{
	static int busy = 0;
	static int skip = 0;
	if (!s_open || busy) return;
	if (++skip < 24) return;
	skip = 0;
	busy = 1;
	AmigaAudio_MusicService();
	busy = 0;
}
