/*
 * SDLmini - RWops.
 *
 * OpenXcom uses these for exactly two things: wrapping a block of memory that
 * already holds a decoded sound, and loading a BMP font through
 * SDL_LoadBMP_RW. Files are read with stdio, memory with a cursor.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "sdlmini.h"

/* --------------------------------------------------------------- memory -- */

static int mem_seek(SDL_RWops *ctx, int offset, int whence)
{
	Uint8 *base = ctx->hidden.mem.base;
	Uint8 *stop = ctx->hidden.mem.stop;
	Uint8 *pos;

	switch (whence) {
		case RW_SEEK_SET: pos = base + offset; break;
		case RW_SEEK_CUR: pos = ctx->hidden.mem.here + offset; break;
		case RW_SEEK_END: pos = stop + offset; break;
		default: return -1;
	}
	if (pos < base) pos = base;
	if (pos > stop) pos = stop;
	ctx->hidden.mem.here = pos;
	return (int)(pos - base);
}

static int mem_read(SDL_RWops *ctx, void *ptr, int size, int maxnum)
{
	int avail = (int)(ctx->hidden.mem.stop - ctx->hidden.mem.here);
	int total;

	if (size <= 0 || maxnum <= 0 || avail <= 0) return 0;
	total = avail / size;
	if (total > maxnum) total = maxnum;
	memcpy(ptr, ctx->hidden.mem.here, (size_t)(total * size));
	ctx->hidden.mem.here += total * size;
	return total;
}

static int mem_write(SDL_RWops *ctx, const void *ptr, int size, int num)
{
	int avail = (int)(ctx->hidden.mem.stop - ctx->hidden.mem.here);
	int total = num;
	if (total * size > avail) total = avail / size;
	if (total <= 0) return 0;
	memcpy(ctx->hidden.mem.here, ptr, (size_t)(total * size));
	ctx->hidden.mem.here += total * size;
	return total;
}

static int mem_close(SDL_RWops *ctx)
{
	if (ctx != NULL) SDL_FreeRW(ctx);
	return 0;
}

SDL_RWops *SDL_AllocRW(void)
{
	return (SDL_RWops *)calloc(1, sizeof(SDL_RWops));
}

void SDL_FreeRW(SDL_RWops *area)
{
	free(area);
}

SDL_RWops *SDL_RWFromMem(void *mem, int size)
{
	SDL_RWops *rw = SDL_AllocRW();
	if (rw == NULL) return NULL;
	rw->type = 1;
	rw->hidden.mem.base = (Uint8 *)mem;
	rw->hidden.mem.here = (Uint8 *)mem;
	rw->hidden.mem.stop = (Uint8 *)mem + size;
	rw->seek  = mem_seek;
	rw->read  = mem_read;
	rw->write = mem_write;
	rw->close = mem_close;
	return rw;
}

SDL_RWops *SDL_RWFromConstMem(const void *mem, int size)
{
	SDL_RWops *rw = SDL_RWFromMem((void *)mem, size);
	if (rw != NULL) rw->write = NULL;
	return rw;
}

/* ----------------------------------------------------------------- file -- */

static int file_seek(SDL_RWops *ctx, int offset, int whence)
{
	FILE *fp = (FILE *)ctx->hidden.unknown.data1;
	int   w  = (whence == RW_SEEK_SET) ? SEEK_SET : (whence == RW_SEEK_CUR) ? SEEK_CUR : SEEK_END;
	if (fseek(fp, offset, w) != 0) return -1;
	return (int)ftell(fp);
}

static int file_read(SDL_RWops *ctx, void *ptr, int size, int maxnum)
{
	FILE *fp = (FILE *)ctx->hidden.unknown.data1;
	return (int)fread(ptr, (size_t)size, (size_t)maxnum, fp);
}

static int file_write(SDL_RWops *ctx, const void *ptr, int size, int num)
{
	FILE *fp = (FILE *)ctx->hidden.unknown.data1;
	return (int)fwrite(ptr, (size_t)size, (size_t)num, fp);
}

static int file_close(SDL_RWops *ctx)
{
	if (ctx == NULL) return 0;
	fclose((FILE *)ctx->hidden.unknown.data1);
	SDL_FreeRW(ctx);
	return 0;
}

SDL_RWops *SDL_RWFromFile(const char *file, const char *mode)
{
	FILE *fp;
	SDL_RWops *rw;

	fp = fopen(file, mode);
	if (fp == NULL) {
		SDL_SetError("SDLmini: cannot open %s", file);
		return NULL;
	}
	rw = SDL_AllocRW();
	if (rw == NULL) { fclose(fp); return NULL; }

	rw->type = 2;
	rw->hidden.unknown.data1 = fp;
	rw->seek  = file_seek;
	rw->read  = file_read;
	rw->write = file_write;
	rw->close = file_close;
	return rw;
}

SDL_RWops *SDL_RWFromFP(FILE *fp, int autoclose)
{
	SDL_RWops *rw = SDL_AllocRW();
	if (rw == NULL) return NULL;
	(void)autoclose;
	rw->type = 2;
	rw->hidden.unknown.data1 = fp;
	rw->seek  = file_seek;
	rw->read  = file_read;
	rw->write = file_write;
	rw->close = file_close;
	return rw;
}
