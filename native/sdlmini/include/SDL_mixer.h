/*
 * SDLmini - the SDL_mixer 1.2 API, as much of it as OpenXcom calls.
 *
 * Backed by Paula directly (native/amiga_audio.c), not by a mixer: four
 * hardware channels, one sound each, no software mixing. The struct and
 * prototype shapes match SDL_mixer 1.2 so the game code compiles unmodified;
 * the semantics are documented per function in sdlmini_mixer.c where they
 * differ.
 */
#ifndef SDLMINI_SDL_MIXER_H
#define SDLMINI_SDL_MIXER_H

#include "SDL.h"
#include "SDL_rwops.h"
#include "SDL_audio.h"

#ifdef __cplusplus
extern "C" {
#endif

/* SDL_MIX_MAXVOLUME already comes from SDL_audio.h and is the same 128. */
#define MIX_MAX_VOLUME     SDL_MIX_MAXVOLUME
#define MIX_DEFAULT_FORMAT AUDIO_S16SYS

typedef struct Mix_Chunk {
	int    allocated;
	Uint8 *abuf;         /* 8-bit signed mono, in Chip RAM, ready for Paula */
	Uint32 alen;
	Uint8  volume;       /* 0 - MIX_MAX_VOLUME */
} Mix_Chunk;

typedef struct _Mix_Music Mix_Music;

typedef enum {
	MUS_NONE, MUS_CMD, MUS_WAV, MUS_MOD, MUS_MID,
	MUS_OGG, MUS_MP3, MUS_MP3_MAD, MUS_FLAC, MUS_MODPLUG
} Mix_MusicType;

extern int  Mix_OpenAudio(int frequency, Uint16 format, int channels, int chunksize);
extern void Mix_CloseAudio(void);
extern int  Mix_AllocateChannels(int numchans);
extern int  Mix_ReserveChannels(int num);
extern int  Mix_GroupChannels(int from, int to, int tag);
extern int  Mix_GroupAvailable(int tag);

extern Mix_Chunk *Mix_LoadWAV_RW(SDL_RWops *src, int freesrc);
extern Mix_Chunk *Mix_LoadWAV(const char *file);
extern void       Mix_FreeChunk(Mix_Chunk *chunk);

extern int Mix_PlayChannel(int channel, Mix_Chunk *chunk, int loops);
extern int Mix_PlayChannelTimed(int channel, Mix_Chunk *chunk, int loops, int ticks);
extern int Mix_HaltChannel(int channel);
extern int Mix_Playing(int channel);
extern int Mix_Volume(int channel, int volume);
extern int Mix_FadeOutChannel(int which, int ms);
extern int Mix_SetPosition(int channel, Sint16 angle, Uint8 distance);

extern Mix_Music    *Mix_LoadMUS(const char *file);
extern Mix_Music    *Mix_LoadMUS_RW(SDL_RWops *rw);
extern void          Mix_FreeMusic(Mix_Music *music);
extern int           Mix_PlayMusic(Mix_Music *music, int loops);
extern int           Mix_VolumeMusic(int volume);
extern int           Mix_HaltMusic(void);
extern int           Mix_FadeOutMusic(int ms);
extern void          Mix_PauseMusic(void);
extern void          Mix_ResumeMusic(void);
extern int           Mix_PlayingMusic(void);
extern Mix_MusicType Mix_GetMusicType(const Mix_Music *music);
extern void          Mix_HookMusic(void (*mix_func)(void *udata, Uint8 *stream, int len), void *arg);
extern void          Mix_HookMusicFinished(void (*music_finished)(void));

extern const char *Mix_GetError(void);

/* Called once per frame from the game loop to keep streaming music fed.
 * Not part of SDL_mixer: there is no mixer thread here to do it for us. */
extern void SDLmini_MixerService(void);

#ifdef __cplusplus
}
#endif

#endif /* SDLMINI_SDL_MIXER_H */
