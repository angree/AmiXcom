#!/bin/sh
#
# Amiga OpenXcom - build the 68k binary.
#
# Run inside WSL:  sh /mnt/i/GITHUB/Amiga_OpenXCOM/build/build.sh [aga|rtg|ask]
#
# The tree is assembled fresh from the pristine upstream tarball on every run,
# so the repository never holds a modified copy of OpenXcom and the port stays
# a patch set plus native/ - the same model as openttd_amiga_68k.
#
# Toolchain traps inherited from that port (see its BUILDING.md, they cost days
# to rediscover):
#   -O2 breaks C++ exception unwinding  -> build at -O1
#   -m68040 silently selects the 68881 multilib even with -msoft-float
#                                       -> use -mcpu=68020 -msoft-float
#   -lpthread / -lc pull newlib in beside libnix -> never link them
#
set -e

REPO=/mnt/i/GITHUB/Amiga_OpenXCOM
WORK=$HOME/build
SRC=$WORK/openxcom
YAML=$WORK/yamlcpp063
JOBS=$(nproc 2>/dev/null || echo 4)

export PATH=/opt/amiga/bin:/usr/local/bin:/usr/bin:/bin

# The repository lives on a Windows drive, which WSL reaches through drvfs.
# Compiling with include paths pointing there is several times slower than
# compiling the same files from the Linux filesystem - the compiler stats and
# opens headers thousands of times. So native/ is mirrored into the build
# directory first and everything below refers to the mirror.
NATIVE=$WORK/native

# Where the emulated Amiga sees Work:. On the SSD, not in the repository: the
# repo is on a network drive and WinUAE mounting ~10k small game-data files
# across it is slow enough to matter for every single test run.
DEPLOY=/mnt/c/temp/amiga_oxcom/work

# AMIGA_FPU=1 builds the same sources against the 68881 multilib instead of
# soft float. EXPERIMENT (2026-08-18): with hardware FP the game never calls
# mathieee*.library, which is what makes one mouse move on the geoscape cost
# ~370 ms on a machine that HAS an FPU. Binaries are named
# openxcom-<backend>-fpu and use their own object directory, so the normal
# soft-float build is untouched. NOTE: libnix has no 68881 multilib (only
# libm.a), so anything in libnix returning a double returns it the soft way
# - treat wrong numbers in this build as that, not as a game bug.
if [ "$AMIGA_FPU" = "1" ]; then
	CPU="-mcpu=68020 -m68881"
	DEFS_FPU="-DAMIGA_FPU_BUILD"
	FPUSUF="-fpu"
else
	CPU="-mcpu=68020 -msoft-float"
	FPUSUF=""
fi
OPT="-O1"
COMMON="$CPU $OPT -noixemul -fomit-frame-pointer"
# __NO_OPENGL and __NO_MUSIC are upstream's own switches: the first compiles
# OpenGL.cpp away to nothing, the second removes the music player (which on
# this port is replaced by streamed ADPCM in a later stage, not by SDL_mixer).
DEFS="-D__AMIGA__ -D__NO_OPENGL -D__NO_MUSIC -DYAML_CPP_STATIC_DEFINE $DEFS_FPU"
# cgx-include holds the CyberGraphX developer headers the RTG path needs; they
# are not in the toolchain and not redistributable, so they are supplied by the
# user (see native/cgx-include/README).
INCS="-I$SRC/src -I$NATIVE/sdlmini/include -I$NATIVE -I$NATIVE/cgx-include -I$YAML/include"

CFLAGS="$COMMON $DEFS $INCS"
# RTTI stays on: the game uses dynamic_cast in several states (BriefingState
# among them). Exceptions likewise - saveload throws by design.
CXXFLAGS="$COMMON -std=gnu++11 -fpermissive $DEFS $INCS"

log() { echo "== $*"; }

# ---------------------------------------------------------------- sources --

if [ ! -d "$SRC" ] || [ "$1" = "clean" ]; then
	log "unpacking pristine upstream"
	rm -rf "$SRC"
	mkdir -p "$WORK"
	( cd "$WORK" && tar xzf "$REPO/upstream/openxcom-00fbacde.tar.gz" &&
	  mv OpenXcom-00fbacde3b52113e175dda6f6d51fe42073c7424 openxcom )
fi

log "mirroring native/ into the Linux filesystem"
mkdir -p "$NATIVE"
cp -r "$REPO/native/." "$NATIVE/"
# splash backgrounds/logo embedded in the binary (build/gen_splash.py)
python3 "$REPO/build/gen_splash.py" "$REPO/intro" "$NATIVE/amiga_splash_data.c"

log "applying Amiga patches"
python3 "$REPO/build/apply-amiga-patches.py" "$SRC/src" "$YAML"

# ------------------------------------------------------------------ build --

OBJ=$WORK/obj$FPUSUF
mkdir -p "$OBJ"

# Is any file the object depends on newer than the object? The dependency list
# is the .d file the previous compile wrote with -MMD (source + every header it
# pulled in). Without this the build only compared the .cpp against the .o, so
# a change to a HEADER left every other translation unit that included it
# stale. That is not a "slightly old binary": a class that grew a member
# (Globe.h, 2026-08-16) was still `new`-ed with the OLD sizeof by GeoscapeState,
# the constructor wrote past the allocation, and the symptoms were random heap
# corruption - a shader reading zeros from a table that was proven correct, a
# colour key vanishing from a surface, the ocean disappearing at zoom. Hours.
needs_build() {   # $1 = source, $2 = object
	[ -f "$2" ] || return 0
	[ "$1" -nt "$2" ] && return 0
	if [ -f "$2.d" ]; then
		# .d format: "obj: src hdr hdr \" continued over lines; -MP adds
		# phony targets ("hdr:") which we drop.
		for dep in $(sed -e 's/\\$//' -e 's/^[^:]*://' "$2.d" | tr ' ' '\n' | grep -v ':$' | grep -v '^$'); do
			[ -f "$dep" ] || return 0        # a dependency vanished: rebuild
			[ "$dep" -nt "$2" ] && return 0
		done
		return 1
	fi
	return 0   # no dependency info yet: rebuild once so it gets written
}

compile_c() {
	out="$OBJ/$(echo "$2" | tr / _).o"
	if needs_build "$1/$2" "$out"; then
		m68k-amigaos-gcc $CFLAGS -MMD -MP -MF "$out.d" -c "$1/$2" -o "$out" || exit 1
	fi
	echo "$out"
}

# cc1plus segfaults on some of these files under WSL1: GCC's own recursion in
# the RTL passes overflows the 8 MB stack WSL1 gives a process, and it looks
# exactly like a compiler bug. Raising the limit fixes most of it; whatever
# still ICEs is retried at -O0, which uses far less stack. Files that end up at
# -O0 are listed at the end of the build, because they are a real speed cost on
# a 68020 and should not quietly accumulate.
ulimit -s 65536 2>/dev/null || true
: > "$WORK/ice.list"

compile_cxx() {
	out="$OBJ/$(echo "$2" | tr / _).o"
	# Mod.cpp MUST stay at -O0: gcc 6.5 miscompiles it at -O1 (even with
	# -fno-inline) - black palettes everywhere past the main menu, proven
	# by bisection 2026-08-17. Not a suspect: a conviction.
	if [ "$2" = "Mod/Mod.cpp" ]; then
		if needs_build "$1/$2" "$out"; then
			if ! m68k-amigaos-g++ $(echo "$CXXFLAGS" | sed 's/-O1/-O0/') -MMD -MP -MF "$out.d" -c "$1/$2" -o "$out" 2>"$WORK/cc.err"; then
				echo "FAILED: $1/$2" >&2; cat "$WORK/cc.err" >&2; exit 1
			fi
		fi
		echo "$out"
		return
	fi
	if needs_build "$1/$2" "$out"; then
		if ! m68k-amigaos-g++ $CXXFLAGS -MMD -MP -MF "$out.d" -c "$1/$2" -o "$out" 2>"$WORK/cc.err"; then
			if grep -q "internal compiler error" "$WORK/cc.err"; then
				# gcc 6.5 ICEs on the inlined yaml-cpp set_data cluster at -O1;
				# -fno-inline dodges it, far cheaper than the -O0 fallback below.
				if m68k-amigaos-g++ $CXXFLAGS -fno-inline -MMD -MP -MF "$out.d" -c "$1/$2" -o "$out" 2>"$WORK/cc.err"; then
					echo "$2 (-O1 -fno-inline)" >> "$WORK/ice.list"
					echo "$out"
					return
				fi
				echo "$2 (-O0)" >> "$WORK/ice.list"
				if ! m68k-amigaos-g++ $(echo "$CXXFLAGS" | sed 's/-O1/-O0/') \
				     -MMD -MP -MF "$out.d" -c "$1/$2" -o "$out" 2>"$WORK/cc.err"; then
					echo "FAILED (even at -O0): $1/$2" >&2
					cat "$WORK/cc.err" >&2
					exit 1
				fi
			else
				echo "FAILED: $1/$2" >&2
				cat "$WORK/cc.err" >&2
				exit 1
			fi
		fi
	fi
	echo "$out"
}

# The game, minus everything the port removes: OpenGL, the scalers and the
# zoom path that only exists to feed them.
log "collecting game sources"
( cd "$SRC/src" && find . -name '*.cpp' \
	! -path './Engine/Scalers/*' \
	! -path './pch.cpp' \
	| sed 's|^\./||' | sort ) > "$WORK/game.list"

log "compiling SDLmini + native layer"
NATIVE_OBJS=""
for f in sdlmini_core.c sdlmini_video.c sdlmini_events.c sdlmini_rwops.c \
         sdlmini_bmp.c sdlmini_thread.c sdlmini_mixer.c sdlmini_gfx.c \
         sdlmini_image.c sdlmini_lbm.c sdlmini_sleep.c sdlmini_autoinput.c; do
	NATIVE_OBJS="$NATIVE_OBJS $(compile_c "$NATIVE/sdlmini/src" "$f")"
done
# fp_conv.c / fp_single.c: soft-float routines that must NOT come from the
# toolchain. libnix's libm.a maps float multiply/divide onto the ROM
# mathieeesingbas.library, whose no-FPU Mul/Div entries are broken in
# Kickstart 3.1 (Guru 8000000B on the first float division - see PROGRESS.md
# and the header of fp_single.c). Linking these objects ahead of -lm binds
# the symbols here; libm's stub members are never pulled in.
# amiga_trap.c: task-level CPU exception handler; a Guru becomes a log line
# with the faulting PC (armed in main.cpp by the patch script).
# libnix_fixes.c: libc routines libnix gets wrong (wmemcpy copies half of a
# wide string; that garbled every std::wstring in the game).
for f in amiga_gfx.c amiga_audio.c amiga_adpcm.c amiga_startup.c amiga_stack.c \
         fp_conv.c fp_single.c amiga_trap.c libnix_fixes.c amiga_splash.c amiga_splash_data.c; do
	NATIVE_OBJS="$NATIVE_OBJS $(compile_c "$NATIVE" "$f")"
done

log "assembling c2p"
# Kalms' routines are Motorola syntax, which vasm (shipped with amiga-gcc)
# assembles directly. The NDK assembler includes are not on vasm's default
# search path, hence -I.
vasmm68k_mot -Fhunk -m68020 -no-opt \
	-I/opt/amiga/m68k-amigaos/ndk-include \
	-o "$OBJ/c2p_glue.o" "$NATIVE/c2p_glue.s"
NATIVE_OBJS="$NATIVE_OBJS $OBJ/c2p_glue.o"

# yaml-cpp is compiled as ONE translation unit, on purpose.
#
# The AmigaOS Hunk object format has no COMDAT: when the same template
# instantiation appears in several objects, the linker keeps one copy and warns
# "duplicate section ... has different size". Keeping the wrong copy is not
# theoretical - with yaml-cpp built per-file, YAML::LoadFile() on a two-line
# metadata.yml never returns, and with the exact same sources built as a single
# TU it parses instantly. The regex matcher is the victim; the warnings name it.
#
# One TU means no cross-object duplicates to resolve, and the build is faster
# as a bonus.
log "compiling yaml-cpp (single translation unit)"
( cd "$YAML/src" && ls *.cpp contrib/*.cpp 2>/dev/null | sed 's|^|#include "|; s|$|"|' ) > "$WORK/yaml_all.cpp"
YAML_OBJS="$OBJ/yaml_all.o"
if [ ! -f "$YAML_OBJS" ] || [ "$WORK/yaml_all.cpp" -nt "$YAML_OBJS" ]; then
	m68k-amigaos-g++ $CXXFLAGS -I"$YAML/src" -c "$WORK/yaml_all.cpp" -o "$YAML_OBJS"
fi

log "compiling the game ($(wc -l < "$WORK/game.list") files)"
GAME_OBJS=""
while read -r f; do
	GAME_OBJS="$GAME_OBJS $(compile_cxx "$SRC/src" "$f")"
done < "$WORK/game.list"

if [ -s "$WORK/ice.list" ]; then
	log "compiled at -O0 after a compiler ICE (speed cost, revisit):"
	sed 's/^/    /' "$WORK/ice.list"
fi

# Three binaries, one code base. Only the compiled-in display default differs,
# so a fix lands in all three at once; each still takes -aga / -rtg / -ask.
log "linking the three variants"
mkdir -p "$DEPLOY"

link_variant() {
	name=$1
	default=$2

	m68k-amigaos-gcc $CFLAGS -DAMIGA_BACKEND_DEFAULT=$default \
		-c "$NATIVE/sdlmini/src/sdlmini_backend.c" -o "$OBJ/backend_$name.o"

	m68k-amigaos-g++ $COMMON -o "$WORK/openxcom-$name$FPUSUF" \
		$GAME_OBJS $NATIVE_OBJS "$OBJ/backend_$name.o" $YAML_OBJS -lamiga -lm

	# DO NOT STRIP. m68k-amigaos-strip produces a Hunk executable that loads
	# and then takes the whole machine down - WinUAE stops the CPU with HALT1,
	# black screen, no Guru, no output, and it looks exactly like the program
	# crashing on startup. Proven with a 10 KB hello-world: unstripped runs,
	# stripped is silent. (The openttd port configures with --disable-strip,
	# which is the same conclusion reached from the other direction.)
	# The cost is ~3 MB of symbols in a 15 MB binary; correctness first.
	cp "$WORK/openxcom-$name$FPUSUF" "$DEPLOY/openxcom-$name$FPUSUF"
	ls -la "$WORK/openxcom-$name$FPUSUF"
}

link_variant aga 0     # AGA screen + chunky-to-planar
link_variant rtg 1     # 8-bit CyberGraphX / Picasso96 screen
link_variant ask -1    # Intuition requester at startup

# The game's own data (rulesets, languages, shaders) lives in bin/ upstream and
# is what "PROGDIR:data/" resolves to on the Amiga side. Copied without
# overwriting, so the original X-COM files the player drops into data/UFO and
# data/TFTD are never touched by a build.
log "deploying game data (no overwrite)"
mkdir -p "$DEPLOY/data"
cp -rn "$SRC/bin/." "$DEPLOY/data/" 2>/dev/null || true
# the port adds strings to the common language file - always refresh that one
cp "$SRC/bin/common/Language/en-US.yml" "$DEPLOY/data/common/Language/en-US.yml"
# precomputed globe shadow normals (see build/gen_earthfix.py) - regenerated
# only when missing or the generator is newer
if [ ! -f "$DEPLOY/data/common/earthfix.dat" ] || [ "$REPO/build/gen_earthfix.py" -nt "$DEPLOY/data/common/earthfix.dat" ]; then
	python3 "$REPO/build/gen_earthfix.py" "$DEPLOY/data/common/earthfix.dat"
fi

log "deployed to $DEPLOY"
log "done"
