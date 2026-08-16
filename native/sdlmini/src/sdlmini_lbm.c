/*
 * SDLmini - IFF ILBM / PBM loader.
 *
 * X-COM's UFOGRAPH/*.LBM are Deluxe Paint II "PBM " files: FORM/PBM, 320x200,
 * 8 planes, one 256-entry CMAP, and a BODY compressed with ByteRun1. The game
 * reaches them through IMG_Load(), so without this the port stops at the first
 * battlescape resource.
 *
 * ILBM (planar, the Amiga's own flavour of the same container) is decoded too.
 * Nothing here produces it, but a mod might, and deinterleaving eight planes is
 * twenty lines - cheaper than another debugging session over a black screen.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SDL.h"
#include "SDL_image.h"
#include "sdlmini.h"

#define ID(a, b, c, d) (((Uint32)(a) << 24) | ((Uint32)(b) << 16) | ((Uint32)(c) << 8) | (Uint32)(d))

static Uint32 be32(const Uint8 *p)
{
	return ((Uint32)p[0] << 24) | ((Uint32)p[1] << 16) | ((Uint32)p[2] << 8) | (Uint32)p[3];
}

static Uint16 be16(const Uint8 *p)
{
	return (Uint16)(((Uint16)p[0] << 8) | (Uint16)p[1]);
}

/* ByteRun1, the only compression IFF ever really used. Decodes at most
 * `outmax` bytes and stops early rather than running off either buffer - a
 * truncated LBM must not take the machine down. */
static Uint32 unpack_byterun1(const Uint8 *src, Uint32 srclen, Uint8 *dst, Uint32 outmax)
{
	Uint32 in = 0, out = 0;

	while (in < srclen && out < outmax) {
		int n = (int)(signed char)src[in++];

		if (n >= 0) {
			Uint32 count = (Uint32)n + 1;
			if (in + count > srclen) count = srclen - in;
			if (out + count > outmax) count = outmax - out;
			memcpy(dst + out, src + in, count);
			in  += count;
			out += count;
		} else if (n != -128) {
			Uint32 count = (Uint32)(-n) + 1;
			Uint8 v;
			if (in >= srclen) break;
			v = src[in++];
			if (out + count > outmax) count = outmax - out;
			memset(dst + out, v, count);
			out += count;
		}
		/* n == -128 is a no-op by definition */
	}
	return out;
}

SDL_Surface *SDLmini_LoadLBM(const Uint8 *data, Uint32 size)
{
	Uint32 pos = 12;
	int w = 0, h = 0, planes = 0, compression = 0, masking = 0;
	int isPBM;
	const Uint8 *cmap = NULL;
	Uint32 cmaplen = 0;
	const Uint8 *body = NULL;
	Uint32 bodylen = 0;
	SDL_Surface *surf;

	if (size < 20 || be32(data) != ID('F','O','R','M')) {
		SDL_SetError("SDLmini: not an IFF file");
		return NULL;
	}
	isPBM = (be32(data + 8) == ID('P','B','M',' '));
	if (!isPBM && be32(data + 8) != ID('I','L','B','M')) {
		SDL_SetError("SDLmini: IFF file is neither ILBM nor PBM");
		return NULL;
	}

	while (pos + 8 <= size) {
		Uint32 id   = be32(data + pos);
		Uint32 clen = be32(data + pos + 4);
		const Uint8 *b = data + pos + 8;

		if (pos + 8 + clen > size) clen = size - pos - 8;

		if (id == ID('B','M','H','D') && clen >= 12) {
			w           = (int)be16(b + 0);
			h           = (int)be16(b + 2);
			planes      = (int)b[8];
			masking     = (int)b[9];
			compression = (int)b[10];
		} else if (id == ID('C','M','A','P')) {
			cmap    = b;
			cmaplen = clen;
		} else if (id == ID('B','O','D','Y')) {
			body    = b;
			bodylen = clen;
			break;
		}
		pos += 8 + clen + (clen & 1);
	}

	{
		/* This decoder is new, and the port started crashing at random points
		 * in resource loading the moment it went in, so every image it is
		 * handed says what it is until that is settled. */
		char msg[128];
		snprintf(msg, sizeof(msg),
		         "SDLmini: IFF %s %ldx%ld planes %ld compression %ld masking %ld body %lu B of %lu",
		         isPBM ? "PBM" : "ILBM", (long)w, (long)h, (long)planes,
		         (long)compression, (long)masking,
		         (unsigned long)bodylen, (unsigned long)size);
		SDLmini_Log(msg);
	}

	if (w <= 0 || h <= 0 || body == NULL) {
		SDL_SetError("SDLmini: IFF file has no image");
		return NULL;
	}
	if (planes != 8) {
		SDL_SetError("SDLmini: only 8-bit IFF images are supported");
		return NULL;
	}

	surf = SDL_CreateRGBSurface(SDL_SWSURFACE, w, h, 8, 0, 0, 0, 0);
	if (surf == NULL) return NULL;

	{
		/* Rows are stored padded to an even number of bytes, per plane for
		 * ILBM and once for PBM. The whole BODY is one compressed stream. */
		Uint32 rowbytes = (Uint32)((w + 1) & ~1);
		Uint32 planeRow = (Uint32)(((w + 15) / 16) * 2);
		Uint32 rawlen   = isPBM ? rowbytes * (Uint32)h
		                        : planeRow * (Uint32)(planes + (masking == 1 ? 1 : 0)) * (Uint32)h;
		Uint8 *raw = (Uint8 *)malloc(rawlen);
		Uint32 got;

		if (raw == NULL) {
			SDL_FreeSurface(surf);
			SDL_SetError("SDLmini: out of memory unpacking an IFF image");
			return NULL;
		}
		memset(raw, 0, rawlen);

		if (compression == 1) {
			got = unpack_byterun1(body, bodylen, raw, rawlen);
		} else {
			got = bodylen < rawlen ? bodylen : rawlen;
			memcpy(raw, body, got);
		}
		if (got < rawlen) {
			/* Short BODY: keep what arrived rather than refusing the image. */
			SDLmini_Log("SDLmini: IFF image is truncated, showing what there is");
		}

		if (isPBM) {
			int y;
			for (y = 0; y < h; y++) {
				memcpy((Uint8 *)surf->pixels + (Uint32)y * (Uint32)surf->pitch,
				       raw + (Uint32)y * rowbytes, (size_t)w);
			}
		} else {
			int y, p, x;
			Uint32 stride = planeRow * (Uint32)(planes + (masking == 1 ? 1 : 0));
			for (y = 0; y < h; y++) {
				Uint8 *out = (Uint8 *)surf->pixels + (Uint32)y * (Uint32)surf->pitch;
				memset(out, 0, (size_t)w);
				for (p = 0; p < planes; p++) {
					const Uint8 *pl = raw + (Uint32)y * stride + (Uint32)p * planeRow;
					for (x = 0; x < w; x++) {
						if (pl[x >> 3] & (0x80 >> (x & 7))) out[x] |= (Uint8)(1 << p);
					}
				}
			}
		}
		free(raw);
	}

	if (cmap != NULL) {
		SDL_Color colours[256];
		Uint32 n = cmaplen / 3;
		Uint32 i;
		if (n > 256) n = 256;
		for (i = 0; i < n; i++) {
			colours[i].r = cmap[i * 3 + 0];
			colours[i].g = cmap[i * 3 + 1];
			colours[i].b = cmap[i * 3 + 2];
			colours[i].unused = 0;
		}
		SDL_SetColors(surf, colours, 0, (int)n);
	}

	return surf;
}
