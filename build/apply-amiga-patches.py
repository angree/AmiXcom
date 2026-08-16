#!/usr/bin/env python3
"""
Apply the Amiga port's changes to a pristine OpenXcom source tree.

Mechanical and idempotent, on purpose: the repository never stores a modified
copy of OpenXcom, so the port is exactly this script plus native/ - and a
missing patch has to fail loudly rather than leave a subtly different game.

Usage:  apply-amiga-patches.py <path-to-openxcom/src>
"""

import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPLACE = os.path.join(REPO, "native", "oxc-replace")

MARK = "/* AMIGA-PORT:"


def edit(path, old, new, why):
    """Replace `old` with `new` in `path`. Idempotent: if `old` is already
    gone and `new` is present, the patch counts as applied."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()

    if new in text:
        return "already"
    if old not in text:
        raise SystemExit("PATCH FAILED (%s): cannot find in %s:\n%s" % (why, path, old))

    text = text.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    return "applied"


def replace_file(src_root, relative):
    src = os.path.join(REPLACE, relative)
    dst = os.path.join(src_root, relative)
    shutil.copyfile(src, dst)
    return "copied"


def patch_yamlcpp(yamldir):
    """yaml-cpp reads files through std::ifstream, which hangs on close with
    this toolchain (see native/amiga_fstream.h). Both LoadFile entry points are
    rewritten to read the file with stdio and parse from a string."""
    path = os.path.join(yamldir, "src", "parse.cpp")
    if not os.path.isfile(path):
        return "skipped (no yaml-cpp at %s)" % yamldir

    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()
    if "amiga_slurp" in text:
        return "already"

    helper = """
// AMIGA-PORT: std::ifstream::close() never returns on m68k-amigaos libstdc++,
// so the file is read with stdio and parsed from memory instead.
#include <cstdio>
static bool amiga_slurp(const std::string& filename, std::string& out) {
  FILE* f = fopen(filename.c_str(), "rb");
  if (!f) return false;
  char buf[4096];
  size_t n;
  while ((n = fread(buf, 1, sizeof(buf), f)) > 0) out.append(buf, n);
  fclose(f);
  return true;
}
"""
    text = text.replace("namespace YAML {", helper + "\nnamespace YAML {", 1)
    text = text.replace(
        "  std::ifstream fin(filename.c_str());\n"
        "  if (!fin) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return Load(fin);",
        "  std::string text;\n"
        "  if (!amiga_slurp(filename, text)) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return Load(text);")
    text = text.replace(
        "  std::ifstream fin(filename.c_str());\n"
        "  if (!fin) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return LoadAll(fin);",
        "  std::string text;\n"
        "  if (!amiga_slurp(filename, text)) {\n"
        "    throw BadFile();\n"
        "  }\n"
        "  return LoadAll(text);")

    if "amiga_slurp" not in text:
        raise SystemExit("PATCH FAILED: could not rewrite yaml-cpp LoadFile in %s" % path)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)
    return "applied"


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    if len(sys.argv) == 3:
        print("  %-24s %s" % ("yaml-cpp LoadFile", patch_yamlcpp(sys.argv[2])))
    if not os.path.isdir(os.path.join(src, "Engine")):
        raise SystemExit("not an OpenXcom src directory: %s" % src)

    results = []

    # 1. Zoom: upstream scales 320x200 up through SDL_gfx, HQX/xBRZ and SSE2.
    #    The port runs at native resolution and needs none of it.
    results.append(("Engine/Zoom.cpp", replace_file(src, "Engine/Zoom.cpp")))

    # 1b. CrossPlatform: upstream is Win32 + X11 + POSIX in one file, none of
    #     which exists here. Replaced wholesale rather than #ifdef'd.
    results.append(("Engine/CrossPlatform.cpp", replace_file(src, "Engine/CrossPlatform.cpp")))

    # 2. Video defaults. Upstream has a small-screen branch for the Dingoo
    #    handheld that is exactly what an Amiga wants - 320x200, fullscreen,
    #    no async blit - except for the keyboard, which we do have.
    results.append(("Engine/Options.cpp", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "#ifdef DINGOO\n"
        "\t_info.push_back(OptionInfo(\"displayWidth\", &displayWidth, Screen::ORIGINAL_WIDTH));\n"
        "\t_info.push_back(OptionInfo(\"displayHeight\", &displayHeight, Screen::ORIGINAL_HEIGHT));\n"
        "\t_info.push_back(OptionInfo(\"fullscreen\", &fullscreen, true));\n"
        "\t_info.push_back(OptionInfo(\"asyncBlit\", &asyncBlit, false));\n"
        "\t_info.push_back(OptionInfo(\"keyboardMode\", (int*)&keyboardMode, KEYBOARD_OFF));",
        MARK + " Amiga shares the Dingoo small-screen defaults, but has a real keyboard. */\n"
        "#if defined(DINGOO) || defined(__AMIGA__)\n"
        "\t_info.push_back(OptionInfo(\"displayWidth\", &displayWidth, Screen::ORIGINAL_WIDTH));\n"
        "\t_info.push_back(OptionInfo(\"displayHeight\", &displayHeight, Screen::ORIGINAL_HEIGHT));\n"
        "\t_info.push_back(OptionInfo(\"fullscreen\", &fullscreen, true));\n"
        "\t_info.push_back(OptionInfo(\"asyncBlit\", &asyncBlit, false));\n"
        "#ifdef __AMIGA__\n"
        "\t_info.push_back(OptionInfo(\"keyboardMode\", (int*)&keyboardMode, KEYBOARD_ON));\n"
        "#else\n"
        "\t_info.push_back(OptionInfo(\"keyboardMode\", (int*)&keyboardMode, KEYBOARD_OFF));\n"
        "#endif",
        "small-screen video defaults")))

    # 2a. Aligned surface buffers. libnix has no posix_memalign, and upstream
    #     already has a branch for exactly this situation - MorphOS uses plain
    #     calloc. AmigaOS joins it: malloc here is AllocMem-backed and hands
    #     out 8-byte aligned blocks, which is all the blitters in this port
    #     need (nothing uses 16-byte SIMD loads on a 68020).
    results.append(("Engine/Surface.cpp", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\t#ifdef __MORPHOS__\n"
        "\n"
        "\tbuffer = calloc( total, 1 );",
        "\t#if defined(__MORPHOS__) || defined(__AMIGA__)\n"
        "\n"
        "\tbuffer = calloc( total, 1 );",
        "no posix_memalign in libnix")))

    # 2b. src/dirent.h is a Microsoft Visual Studio shim whose non-MSVC branch
    #     says #include <dirent.h> - which finds itself again, because the
    #     build puts src/ on the include path. The real libnix dirent.h then
    #     never gets included and getFolderContents does not compile. The shim
    #     has no purpose in this build, so it goes.
    dirent = os.path.join(src, "dirent.h")
    if os.path.exists(dirent):
        os.remove(dirent)
        results.append(("dirent.h", "removed (MSVC shim)"))
    else:
        results.append(("dirent.h", "already"))

    # 3. The one Amiga-specific line in the game's own source: pick the
    #    display before anything opens one. Everything it needs lives in
    #    native/, so this stays a single call rather than a block of code.
    results.append(("main.cpp", edit(
        os.path.join(src, "main.cpp"),
        "\tif (!Options::init(argc, argv))",
        MARK + " choose AGA / RTG (or ask) before any screen exists. */\n"
        "#ifdef __AMIGA__\n"
        "\tamiga_select_backend(argc, argv);\n"
        "#endif\n"
        "\tif (!Options::init(argc, argv))",
        "display backend selection")))

    results.append(("main.cpp (include)", edit(
        os.path.join(src, "main.cpp"),
        "#include \"Menu/StartState.h\"",
        "#include \"Menu/StartState.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#include \"amiga_trap.h\"\n"
        "#include <cstdio>\n"
        "#include <cstdlib>\n"
        "#endif",
        "display backend selection include")))

    # 3b. Name and version of the port. The main menu and the window title
    #     say "AmiXcom 0.1.0 alpha" instead of "OpenXcom 1.0 Dev".
    results.append(("version.h (AmiXcom)", edit(
        os.path.join(src, "version.h"),
        '#define OPENXCOM_VERSION_SHORT "1.0"\n'
        '#define OPENXCOM_VERSION_LONG "1.0.0.0"\n'
        '#define OPENXCOM_VERSION_NUMBER 1,0,0,0\n',
        '#define OPENXCOM_VERSION_SHORT "0.1.0"\n'
        '#define OPENXCOM_VERSION_LONG "0.1.0.0"\n'
        '#define OPENXCOM_VERSION_NUMBER 0,1,0,0\n'
        '#define OPENXCOM_VERSION_GIT " alpha"\n',
        "port version")))
    results.append(("MainMenuState.cpp (AmiXcom title)", edit(
        os.path.join(src, "Menu", "MainMenuState.cpp"),
        '\ttitle << tr("STR_OPENXCOM") << L"\\x02";\n',
        '\ttitle << L"AmiXcom" << L"\\x02";\n',
        "port name in main menu")))
    results.append(("main.cpp (AmiXcom title)", edit(
        os.path.join(src, "main.cpp"),
        '\ttitle << "OpenXcom " << OPENXCOM_VERSION_SHORT << OPENXCOM_VERSION_GIT;\n',
        '\ttitle << "AmiXcom " << OPENXCOM_VERSION_SHORT << OPENXCOM_VERSION_GIT;\n',
        "port name in window title")))

    # 3c. FPS counter on by default - the user wants it in the corner while the
    #     port is being optimised (a fresh options.cfg would otherwise hide it).
    results.append(("Options.cpp (fpsCounter default on)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        '\t_info.push_back(OptionInfo("fpsCounter", &fpsCounter, false));\n',
        '\t_info.push_back(OptionInfo("fpsCounter", &fpsCounter, true)); /* AMIGA-PORT: default on */\n',
        "fps counter default")))

    # 3d. The "Amiga" options tab (step 1 of the user's plan, 2026-08-16):
    #     first tab of the options screen, holding the port's own settings -
    #     Amiga screen title bar on/off and mouse pointer original/Amiga-only.
    #     The screen itself is a new file pair (native/oxc-replace/Menu/
    #     OptionsAmigaState.*); everything below wires it in.
    results.append(("Menu/OptionsAmigaState.h", replace_file(src, os.path.join("Menu", "OptionsAmigaState.h"))))
    results.append(("Menu/OptionsAmigaState.cpp", replace_file(src, os.path.join("Menu", "OptionsAmigaState.cpp"))))
    results.append(("Options.inc.h (amiga options)", edit(
        os.path.join(src, "Engine", "Options.inc.h"),
        "OPT std::string language, useOpenGLShader;\n",
        "OPT std::string language, useOpenGLShader;\n"
        "// AMIGA-PORT: the \"Amiga\" options tab\n"
        "OPT bool amigaAppBar;\n"
        "OPT int amigaCursor;\n",
        "amiga option variables")))
    results.append(("Options.cpp (amiga OptionInfo)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\t_info.push_back(OptionInfo(\"fpsCounter\", &fpsCounter, true)); /* AMIGA-PORT: default on */\n",
        "\t_info.push_back(OptionInfo(\"fpsCounter\", &fpsCounter, true)); /* AMIGA-PORT: default on */\n"
        "\t_info.push_back(OptionInfo(\"amigaAppBar\", &amigaAppBar, false));\n"
        "\t_info.push_back(OptionInfo(\"amigaCursor\", &amigaCursor, 1)); /* default: Amiga pointer */\n",
        "amiga OptionInfo")))
    results.append(("OptionsBaseState.h (btnAmiga)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.h"),
        "\tTextButton *_btnVideo, *_btnAudio, *_btnControls, *_btnGeoscape, *_btnBattlescape, *_btnAdvanced, *_btnMods;\n",
        "\tTextButton *_btnAmiga, *_btnVideo, *_btnAudio, *_btnControls, *_btnGeoscape, *_btnBattlescape, *_btnAdvanced, *_btnMods;\n",
        "amiga tab button member")))
    results.append(("OptionsBaseState.cpp (include)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "#include \"OptionsVideoState.h\"\n",
        "#include \"OptionsVideoState.h\"\n"
        "#include \"OptionsAmigaState.h\"\n",
        "amiga tab include")))
    results.append(("OptionsBaseState.cpp (buttons)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t_btnVideo = new TextButton(80, 16, 8, 8);\n"
        "\t_btnAudio = new TextButton(80, 16, 8, 28);\n"
        "\t_btnControls = new TextButton(80, 16, 8, 48);\n"
        "\t_btnGeoscape = new TextButton(80, 16, 8, 68);\n"
        "\t_btnBattlescape = new TextButton(80, 16, 8, 88);\n"
        "\t_btnAdvanced = new TextButton(80, 16, 8, 108);\n"
        "\t_btnMods = new TextButton(80, 16, 8, 128);\n",
        "\t/* AMIGA-PORT: an eighth tab, \"Amiga\", first; the column is packed to 17 px\n"
        "\t * per button so the tooltip at y=148 keeps its place. */\n"
        "\t_btnAmiga = new TextButton(80, 16, 8, 8);\n"
        "\t_btnVideo = new TextButton(80, 16, 8, 25);\n"
        "\t_btnAudio = new TextButton(80, 16, 8, 42);\n"
        "\t_btnControls = new TextButton(80, 16, 8, 59);\n"
        "\t_btnGeoscape = new TextButton(80, 16, 8, 76);\n"
        "\t_btnBattlescape = new TextButton(80, 16, 8, 93);\n"
        "\t_btnAdvanced = new TextButton(80, 16, 8, 110);\n"
        "\t_btnMods = new TextButton(80, 16, 8, 127);\n",
        "amiga tab button")))
    results.append(("OptionsBaseState.cpp (add)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\tadd(_btnVideo, \"button\", \"optionsMenu\");\n",
        "\tadd(_btnAmiga, \"button\", \"optionsMenu\");\n"
        "\tadd(_btnVideo, \"button\", \"optionsMenu\");\n",
        "amiga tab add")))
    results.append(("OptionsBaseState.cpp (text)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t_btnVideo->setText(tr(\"STR_VIDEO\"));\n",
        "\t_btnAmiga->setText(tr(\"STR_AMIGA\"));\n"
        "\t_btnAmiga->onMousePress((ActionHandler)&OptionsBaseState::btnGroupPress, SDL_BUTTON_LEFT);\n"
        "\n"
        "\t_btnVideo->setText(tr(\"STR_VIDEO\"));\n",
        "amiga tab text")))
    results.append(("OptionsBaseState.cpp (group)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t_group = button;\n"
        "\t_btnVideo->setGroup(&_group);\n",
        "\t_group = button;\n"
        "\t_btnAmiga->setGroup(&_group);\n"
        "\t_btnVideo->setGroup(&_group);\n",
        "amiga tab group")))
    results.append(("OptionsBaseState.cpp (press)", edit(
        os.path.join(src, "Menu", "OptionsBaseState.cpp"),
        "\t\tif (sender == _btnVideo)\n"
        "\t\t{\n"
        "\t\t\t_game->pushState(new OptionsVideoState(_origin));\n"
        "\t\t}\n",
        "\t\tif (sender == _btnAmiga)\n"
        "\t\t{\n"
        "\t\t\t_game->pushState(new OptionsAmigaState(_origin));\n"
        "\t\t}\n"
        "\t\telse if (sender == _btnVideo)\n"
        "\t\t{\n"
        "\t\t\t_game->pushState(new OptionsVideoState(_origin));\n"
        "\t\t}\n",
        "amiga tab press")))
    results.append(("en-US.yml (amiga strings)", edit(
        os.path.join(src, "..", "bin", "common", "Language", "en-US.yml"),
        "  STR_MODS: \"MODS\"\n",
        "  STR_MODS: \"MODS\"\n"
        "  STR_AMIGA: \"AMIGA\"\n"
        "  STR_AMIGA_APP_BAR: \"Amiga screen title bar\"\n"
        "  STR_AMIGA_APP_BAR_DESC: \"Keep the Amiga screen title bar (with the depth gadget) so you can flip to Workbench. Opens a 320x256 screen. Takes effect at the next start.\"\n"
        "  STR_AMIGA_CURSOR: \"Mouse pointer\"\n"
        "  STR_AMIGA_CURSOR_DESC: \"Original: the game draws its own cursor. Amiga: only the system pointer is shown - nothing to redraw, so it moves smoothly.\"\n"
        "  STR_AMIGA_CURSOR_ORIGINAL: \"Original (game-drawn)\"\n"
        "  STR_AMIGA_CURSOR_AMIGA: \"Amiga pointer only\"\n"
        "  STR_AMIGA_OFF: \"Off\"\n"
        "  STR_AMIGA_ON: \"On\"\n",
        "amiga language strings")))
    # 4. Startup markers. An early crash on this hardware does not produce a
    #    Guru - the CPU double-faults and the emulator stops dead - so the only
    #    way to know how far the game got is a line written and flushed at each
    #    step. Removed once the port starts reliably.
    results.append(("main.cpp (markers)", edit(
        os.path.join(src, "main.cpp"),
        "\tgame = new Game(title.str());\n"
        "\tState::setGamePtr(game);\n"
        "\tgame->setState(new StartState);\n"
        "\tgame->run();",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"main: options initialised\");\n"
        "#endif\n"
        "\tgame = new Game(title.str());\n"
        "\tState::setGamePtr(game);\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"main: game constructed\");\n"
        "#endif\n"
        "\tgame->setState(new StartState);\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"main: entering main loop\");\n"
        "\t/* AMIGA-PORT: a CPU exception anywhere below lands here with the\n"
        "\t * faulting PC and registers, logs them, and exits - instead of a\n"
        "\t * Software Failure requester that says only #8000000B. */\n"
        "\tif (amiga_trap_arm())\n"
        "\t{\n"
        "\t\tchar b[2048];\n"
        "\t\tamiga_trap_describe(b, sizeof(b));\n"
        "\t\tSDLmini_Log(b);\n"
        "\t\tLog(LOG_FATAL) << b;\n"
        "\t\tamiga_trap_disarm();\n"
        "\t\texit(20);\n"
        "\t}\n"
        "#endif\n"
        "\tgame->run();",
        "startup markers")))

    # 5. Markers inside Options::init. The port currently hangs somewhere in
    #    here, before the game's own log file exists, so these are the only
    #    visible steps. Removed once startup is reliable.
    results.append(("Engine/Options.cpp (markers)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\tcreate();\n"
        "\tresetDefault();\n"
        "\tloadArgs(argc, argv);\n"
        "\tsetFolders();\n"
        "\t_setDefaultMods();\n"
        "\tupdateOptions();",
        "#ifdef __AMIGA__\n"
        "#define AMIGA_STEP(x) SDLmini_Log(\"options: \" x)\n"
        "#else\n"
        "#define AMIGA_STEP(x)\n"
        "#endif\n"
        "\tAMIGA_STEP(\"create\");\n"
        "\tcreate();\n"
        "\tAMIGA_STEP(\"resetDefault\");\n"
        "\tresetDefault();\n"
        "\tAMIGA_STEP(\"loadArgs\");\n"
        "\tloadArgs(argc, argv);\n"
        "\tAMIGA_STEP(\"setFolders\");\n"
        "\tsetFolders();\n"
        "\tAMIGA_STEP(\"_setDefaultMods\");\n"
        "\t_setDefaultMods();\n"
        "\tAMIGA_STEP(\"updateOptions\");\n"
        "\tupdateOptions();\n"
        "\tAMIGA_STEP(\"options done\");",
        "Options::init markers")))

    results.append(("Engine/Options.cpp (mod markers)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "\tFileMap::load(\"common\", CrossPlatform::searchDataFolder(\"common\"), true);\n"
        "\n"
        "\tstd::string modPath = CrossPlatform::searchDataFolder(\"standard\");",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: loading common\");\n"
        "#endif\n"
        "\tFileMap::load(\"common\", CrossPlatform::searchDataFolder(\"common\"), true);\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: common loaded\");\n"
        "#endif\n"
        "\n"
        "\tstd::string modPath = CrossPlatform::searchDataFolder(\"standard\");",
        "updateMods markers")))

    # 5b. Markers around resource loading. Mod::loadResources writes nothing
    #     to the game's own log, so a crash in the middle of the sound sets is
    #     otherwise indistinguishable from a hang. Removed once startup is
    #     reliable.
    results.append(("Mod/Mod.cpp (resource markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\t\t\tsound = new SoundSet();\n"
        "\t\t\t\t\t\tsound->loadCat(FileMap::getFilePath(\"SOUND/\" + cats[j][i]), wav);",
        "\t\t\t\t\t\tsound = new SoundSet();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log((\"mods: sound cat \" + cats[j][i]).c_str());\n"
        "#endif\n"
        "\t\t\t\t\t\tsound->loadCat(FileMap::getFilePath(\"SOUND/\" + cats[j][i]), wav);",
        "sound cat marker")))

    results.append(("Mod/Mod.cpp (resources done marker)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tTextButton::soundPress = getSound(\"GEO.CAT\", Mod::BUTTON_PRESS);",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: sounds loaded\");\n"
        "#endif\n"
        "\tTextButton::soundPress = getSound(\"GEO.CAT\", Mod::BUTTON_PRESS);",
        "sounds done marker")))

    results.append(("Mod/Mod.cpp (battlescape marker)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tloadBattlescapeResources(); //",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"mods: loading battlescape resources\");\n"
        "#endif\n"
        "\tloadBattlescapeResources(); //",
        "battlescape resources marker")))

    results.append(("Mod/Mod.cpp (include)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "#include \"Mod.h\"",
        "#include \"Mod.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "Mod.cpp marker include")))

    # 5c. Instrumentation inside SoundSet::loadCat. The CAT index is read
    #     correctly by a standalone test on the same machine but the game gets
    #     absurd object sizes out of it, so the loop logs what it actually sees.
    results.append(("Engine/SoundSet.cpp (cat markers)", edit(
        os.path.join(src, "Engine", "SoundSet.cpp"),
        "\t\tunsigned char *sound = (unsigned char*) sndFile.load(i);\n"
        "\t\tunsigned int size = sndFile.getObjectSize(i);",
        "\t\tunsigned char *sound = (unsigned char*) sndFile.load(i);\n"
        "\t\tunsigned int size = sndFile.getObjectSize(i);\n"
        "#ifdef __AMIGA__\n"
        "\t\tif (i < 3 || size > 1000000) {\n"
        "\t\t\tchar amsg[128];\n"
        "\t\t\tsprintf(amsg, \"cat: %s i=%d/%d size=%lu wav=%d\",\n"
        "\t\t\t        filename.c_str(), i, sndFile.getAmount(),\n"
        "\t\t\t        (unsigned long)size, (int)wav);\n"
        "\t\t\tSDLmini_Log(amsg);\n"
        "\t\t}\n"
        "#endif",
        "loadCat instrumentation")))

    results.append(("Engine/SoundSet.cpp (include)", edit(
        os.path.join(src, "Engine", "SoundSet.cpp"),
        "#include \"SoundSet.h\"",
        "#include \"SoundSet.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include <cstdio>\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "SoundSet.cpp marker include")))

    # 5d. A missing sound CAT is not a reason to lose the game.
    #     Upstream throws when it cannot find the second sound set, which
    #     aborts mod loading and takes the whole game down. On a machine where
    #     the player copies X-COM over by hand, one absent file then looks
    #     exactly like a port bug (it cost a full debugging session here: the
    #     test data has SAMPLE.CAT but no SAMPLE2.CAT). The port logs it and
    #     carries on with a silent sound set instead.
    results.append(("Mod/Mod.cpp (missing sound cat)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\tif (sound == 0)\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\tthrow Exception(catsWin[i] + \" not found\");\n"
        "\t\t\t\t}",
        "\t\t\t\tif (sound == 0)\n"
        "\t\t\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\tLog(LOG_WARNING) << catsWin[i] << \" not found - \" << catsId[i]\n"
        "\t\t\t\t\t          << \" will be silent\";\n"
        "\t\t\t\t\tSDLmini_Log((\"mods: missing sound cat \" + catsWin[i]).c_str());\n"
        "\t\t\t\t\t_sounds[catsId[i]] = new SoundSet();\n"
        "\t\t\t\t\tcontinue;\n"
        "#else\n"
        "\t\t\t\t\tthrow Exception(catsWin[i] + \" not found\");\n"
        "#endif\n"
        "\t\t\t\t}",
        "missing sound cat is not fatal")))

    # 5e. Surface::loadImage sends the path through
    #     wstrToUtf8(fsToWstr(filename)) before IMG_Load, because SDL on a
    #     desktop wants UTF-8. That round trip goes through the C library's
    #     wide-character conversion, which on libnix produces garbage - the
    #     path came out as "P\xe3 \xad\xf5\xa5\xbc\xb0" and every image load
    #     failed with "cannot open". AmigaOS filenames are plain 8-bit bytes,
    #     so the path is handed over untouched.
    results.append(("Engine/Surface.cpp (utf-8 filename round trip)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\t\tstd::string utf8 = Language::wstrToUtf8(Language::fsToWstr(filename));\n"
        "\t\t_surface = IMG_Load(utf8.c_str());",
        "#ifdef __AMIGA__\n"
        "\t\t_surface = IMG_Load(filename.c_str());\n"
        "#else\n"
        "\t\tstd::string utf8 = Language::wstrToUtf8(Language::fsToWstr(filename));\n"
        "\t\t_surface = IMG_Load(utf8.c_str());\n"
        "#endif",
        "no utf-8 round trip on the filename")))

    # 5i. Name every image as it is loaded, through SDLmini's log rather than
    #     the game's. Resource loading crashes at a point that moves between
    #     runs, and the game's own log only names images at verbose level -
    #     which is thousands of lines through the shared folder and slow enough
    #     to change the timing being investigated. This is ~200 lines.
    results.append(("Engine/Surface.cpp (image markers)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "\tLog(LOG_VERBOSE) << \"Loading image: \" << filename;",
        "\tLog(LOG_VERBOSE) << \"Loading image: \" << filename;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log((\"img: \" + filename).c_str());\n"
        "#endif",
        "per-image marker")))

    results.append(("Engine/Surface.cpp (marker include)", edit(
        os.path.join(src, "Engine", "Surface.cpp"),
        "#include \"Surface.h\"",
        "#include \"Surface.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "Surface.cpp marker include")))

    # 5j. The last thing the port logs before it dies is the last extra
    #     resource, globe_ufo.png, which is the one sprite sheet that goes
    #     down the "subdivide into 9 frames with blitNShade at negative
    #     offsets" path. These two markers say whether the crash is inside
    #     that loop or after it.
    results.append(("Mod/Mod.cpp (subdivide markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\t\t\tSurface *temp = new Surface(spritePack->getWidth(), spritePack->getHeight());",
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log(\"subdivide: start\");\n"
        "#endif\n"
        "\t\t\t\t\t\tSurface *temp = new Surface(spritePack->getWidth(), spritePack->getHeight());",
        "subdivide start marker")))

    results.append(("Mod/Mod.cpp (subdivide done marker)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\t\t\t\tdelete temp;",
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log(\"subdivide: blits done\");\n"
        "#endif\n"
        "\t\t\t\t\t\tdelete temp;\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\t\tSDLmini_Log(\"subdivide: temp deleted\");\n"
        "#endif",
        "subdivide done marker")))

    # 5k. modResources() runs after the last resource is loaded and is the
    #     last thing before "Data loaded successfully". It reaches into
    #     _surfaces[...] and _sets[...] by name with operator[], which yields a
    #     NULL pointer for anything the data set does not have - and this data
    #     set is already known to be missing files. A NULL Surface* here is
    #     dereferenced immediately, and on a 68k that reads address 0 (which is
    #     the vector table, i.e. plausible-looking garbage) and then writes
    #     through it: a wild pointer whose address changes run to run, which is
    #     exactly the random Guru we are chasing.
    results.append(("Mod/Mod.cpp (modResources markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\tint newWidth = 320 - 64, newHeight = 200;",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: start\");\n"
        "\t{\n"
        "\t\t/* Name every surface this function assumes exists, before it is\n"
        "\t\t * used. Cheap, and it turns a wild-pointer Guru into a line of\n"
        "\t\t * text naming the missing file. */\n"
        "\t\tstatic const char* const needed[] = {\n"
        "\t\t\t\"GEOBORD.SCR\", \"BACK06.SCR\", \"UNIBORD.PCK\", 0 };\n"
        "\t\tint n_;\n"
        "\t\tfor (n_ = 0; needed[n_]; ++n_)\n"
        "\t\t{\n"
        "\t\t\tif (_surfaces.find(needed[n_]) == _surfaces.end() || _surfaces[needed[n_]] == 0)\n"
        "\t\t\t\tSDLmini_Log((std::string(\"modres: MISSING surface \") + needed[n_]).c_str());\n"
        "\t\t}\n"
        "\t\tif (_sets.find(\"HANDOB.PCK\") == _sets.end() || _sets[\"HANDOB.PCK\"] == 0)\n"
        "\t\t\tSDLmini_Log(\"modres: MISSING set HANDOB.PCK\");\n"
        "\t}\n"
        "#endif\n"
        "\tint newWidth = 320 - 64, newHeight = 200;",
        "modResources start marker")))

    results.append(("Mod/Mod.cpp (modResources altgeobord)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t_surfaces[\"ALTGEOBORD.SCR\"] = newGeo;",
        "\t_surfaces[\"ALTGEOBORD.SCR\"] = newGeo;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: ALTGEOBORD built\");\n"
        "#endif",
        "modResources altgeobord marker")))

    results.append(("Mod/Mod.cpp (modResources back06)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// we create extra rows on the soldier stat screens by shrinking them all down one pixel.",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: ALTBACK07 built\");\n"
        "#endif\n"
        "\t// we create extra rows on the soldier stat screens by shrinking them all down one pixel.",
        "modResources altback07 marker")))

    results.append(("Mod/Mod.cpp (modResources uniborder)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t// now, let's adjust the battlescape info screen.",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: BACK06 adjusted\");\n"
        "#endif\n"
        "\t// now, let's adjust the battlescape info screen.",
        "modResources unibord marker")))

    results.append(("Mod/Mod.cpp (modResources handob)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t_sets[\"HANDOB2.PCK\"] = new SurfaceSet(_sets[\"HANDOB.PCK\"]->getWidth(), _sets[\"HANDOB.PCK\"]->getHeight());",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: UNIBORD adjusted\");\n"
        "#endif\n"
        "\t_sets[\"HANDOB2.PCK\"] = new SurfaceSet(_sets[\"HANDOB.PCK\"]->getWidth(), _sets[\"HANDOB.PCK\"]->getHeight());",
        "modResources handob marker")))

    results.append(("Mod/Mod.cpp (handob loop markers)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\tSurface *surface1 = _sets[\"HANDOB2.PCK\"]->addFrame(i->first);\n"
        "\t\tSurface *surface2 = i->second;\n"
        "\t\tsurface1->setPalette(surface2->getPalette());\n"
        "\t\tsurface2->blit(surface1);",
        "\t\tSurface *surface1 = _sets[\"HANDOB2.PCK\"]->addFrame(i->first);\n"
        "\t\tSurface *surface2 = i->second;\n"
        "#ifdef __AMIGA__\n"
        "\t\t{\n"
        "\t\t\tchar m_[128];\n"
        "\t\t\tsnprintf(m_, sizeof(m_), \"handob: frame %ld src %ldx%ld dst %ldx%ld\",\n"
        "\t\t\t        (long)i->first,\n"
        "\t\t\t        surface2 ? (long)surface2->getWidth() : -1L,\n"
        "\t\t\t        surface2 ? (long)surface2->getHeight() : -1L,\n"
        "\t\t\t        surface1 ? (long)surface1->getWidth() : -1L,\n"
        "\t\t\t        surface1 ? (long)surface1->getHeight() : -1L);\n"
        "\t\t\tSDLmini_Log(m_);\n"
        "\t\t}\n"
        "#endif\n"
        "\t\tsurface1->setPalette(surface2->getPalette());\n"
        "\t\tsurface2->blit(surface1);",
        "handob loop markers")))

    results.append(("Mod/Mod.cpp (modResources done)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\tsurface2->blit(surface1);\n"
        "\t}\n"
        "}",
        "\t\tsurface2->blit(surface1);\n"
        "\t}\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"modres: done\");\n"
        "#endif\n"
        "}",
        "modResources done marker")))

    # 5l. modResources() finishes, so loadAll() and loadMods() both return -
    #     and the very next statement, a Log(LOG_INFO), never appears. Mark
    #     the same points through SDLmini's log, which is a different file
    #     written by different code, so "the game crashed here" and "the
    #     game's logger stopped working here" stop looking identical.
    results.append(("Menu/StartState.cpp (load markers)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tOptions::updateMods();\n"
        "\t\tgame->loadMods();\n"
        "\t\tLog(LOG_INFO) << \"Data loaded successfully.\";",
        "\t\tOptions::updateMods();\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: mods updated, loading them\");\n"
        "#endif\n"
        "\t\tgame->loadMods();\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: loadMods returned\");\n"
        "#endif\n"
        "\t\tLog(LOG_INFO) << \"Data loaded successfully.\";\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: data loaded\");\n"
        "#endif",
        "StartState load markers")))

    results.append(("Menu/StartState.cpp (language markers)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tgame->defaultLanguage();\n"
        "\t\tLog(LOG_INFO) << \"Language loaded successfully.\";\n"
        "\t\tloading = LOADING_SUCCESSFUL;",
        "\t\tgame->defaultLanguage();\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: language loaded\");\n"
        "#endif\n"
        "\t\tLog(LOG_INFO) << \"Language loaded successfully.\";\n"
        "\t\tloading = LOADING_SUCCESSFUL;\n"
        "#ifdef __AMIGA__\n"
        "\t\tSDLmini_Log(\"start: loading marked successful\");\n"
        "#endif",
        "StartState language markers")))

    results.append(("Menu/StartState.cpp (marker include)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "#include \"StartState.h\"",
        "#include \"StartState.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "StartState.cpp marker include")))

    # 5f. First-frame markers in Game::run. Everything up to
    #     "OpenXcom started successfully" is logged by the game itself; the
    #     first drawn frame is not, and that is where the port now dies.
    results.append(("Engine/Game.cpp (frame markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\twhile (!_quit)\n"
        "\t{\n"
        "\t\t// Clean up states",
        "#ifdef __AMIGA__\n"
        "#define AMIGA_FRAME(x) do { static int o_; if (!o_) { o_ = 1; SDLmini_Log(\"frame: \" x); } } while (0)\n"
        "\tSDLmini_Log(\"frame: entering Game::run loop\");\n"
        "#else\n"
        "#define AMIGA_FRAME(x)\n"
        "#endif\n"
        "\twhile (!_quit)\n"
        "\t{\n"
        "\t\tAMIGA_FRAME(\"loop iteration\");\n"
        "\t\t// Clean up states",
        "Game::run frame markers")))

    # 5m. The run stops dead after StartState hands over to the main menu, and
    #     no frame is ever drawn, so the crash is in bringing the new state up.
    #     These markers are NOT one-shot: state changes are what we are
    #     watching, and there are only a handful of them before the menu.
    results.append(("Engine/Game.cpp (state init markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\tif (!_init)\n"
        "\t\t{\n"
        "\t\t\t_init = true;\n"
        "\t\t\t_states.back()->init();\n"
        "\n"
        "\t\t\t// Unpress buttons\n"
        "\t\t\t_states.back()->resetAll();",
        "\t\tif (!_init)\n"
        "\t\t{\n"
        "\t\t\t_init = true;\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"state: init\");\n"
        "#endif\n"
        "\t\t\t_states.back()->init();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"state: init done\");\n"
        "#endif\n"
        "\n"
        "\t\t\t// Unpress buttons\n"
        "\t\t\t_states.back()->resetAll();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"state: resetAll done\");\n"
        "#endif",
        "state init markers")))

    results.append(("Engine/Game.cpp (think markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t// Process logic\n"
        "\t\t\t_states.back()->think();",
        "\t\t\t// Process logic\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: think\");\n"
        "#endif\n"
        "\t\t\t_states.back()->think();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: think done\");\n"
        "#endif",
        "think markers")))

    # 5n. "state: think done" is the last thing the port ever logs. What runs
    #     next is the top of the loop deleting the state that just handed over
    #     - StartState, which owns the loading "thread". Mark the deletion, and
    #     mark each step of that destructor.
    results.append(("Engine/Game.cpp (delete markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\twhile (!_deleted.empty())\n"
        "\t\t{\n"
        "\t\t\tdelete _deleted.back();\n"
        "\t\t\t_deleted.pop_back();\n"
        "\t\t}",
        "\t\twhile (!_deleted.empty())\n"
        "\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: deleting a retired state\");\n"
        "#endif\n"
        "\t\t\tdelete _deleted.back();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"state: retired state deleted\");\n"
        "#endif\n"
        "\t\t\t_deleted.pop_back();\n"
        "\t\t}",
        "retired state delete markers")))

    results.append(("Engine/Game.cpp (post-think markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t_fpsCounter->think();\n"
        "\t\t\tif (Options::FPS > 0 && !(Options::useOpenGL && Options::vSyncForOpenGL))\n"
        "\t\t\t{\n"
        "\t\t\t\t// Update our FPS delay time based on the time of the last draw.\n"
        "\t\t\t\tint fps = SDL_GetAppState() & SDL_APPINPUTFOCUS ? Options::FPS : Options::FPSInactive;\n"
        "\n"
        "\t\t\t\t_timeUntilNextFrame = (1000.0f / fps) - (SDL_GetTicks() - _timeOfLastFrame);\n"
        "\t\t\t}",
        "\t\t\t_fpsCounter->think();\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tAMIGA_FRAME(\"loop: fps counter thought\");\n"
        "#endif\n"
        "\t\t\tif (Options::FPS > 0 && !(Options::useOpenGL && Options::vSyncForOpenGL))\n"
        "\t\t\t{\n"
        "\t\t\t\t// Update our FPS delay time based on the time of the last draw.\n"
        "\t\t\t\tint fps = SDL_GetAppState() & SDL_APPINPUTFOCUS ? Options::FPS : Options::FPSInactive;\n"
        "\n"
        "\t\t\t\t_timeUntilNextFrame = (1000.0f / fps) - (SDL_GetTicks() - _timeOfLastFrame);\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\tAMIGA_FRAME(\"loop: frame delay computed\");\n"
        "#endif\n"
        "\t\t\t}",
        "post-think markers")))

    results.append(("Engine/Game.cpp (delay marker)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t// Save on CPU\n"
        "\t\tswitch (runningState)",
        "#ifdef __AMIGA__\n"
        "\t\tAMIGA_FRAME(\"loop: reached the CPU-saving delay\");\n"
        "#endif\n"
        "\t\t// Save on CPU\n"
        "\t\tswitch (runningState)",
        "delay marker")))

    # Who ends the game? quit() is reached from a Quit button, Ctrl/Amiga+Q,
    # StartState's "any key after a load error", or an SDL_QUIT event; the
    # log otherwise shows a clean exit with no reason at all.
    results.append(("Engine/Game.cpp (quit marker)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "void Game::quit()\n"
        "{\n",
        "void Game::quit()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"game: quit() called\");\n"
        "#endif\n",
        "quit marker")))
    results.append(("Engine/Game.cpp (SDL_QUIT marker)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\tcase SDL_QUIT:\n"
        "\t\t\t\t\tquit();",
        "\t\t\t\tcase SDL_QUIT:\n"
        "#ifdef __AMIGA__\n"
        "\t\t\t\t\tSDLmini_Log(\"game: SDL_QUIT event\");\n"
        "#endif\n"
        "\t\t\t\t\tquit();",
        "SDL_QUIT marker")))
    results.append(("Menu/StartState.cpp (key-quit marker)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\t\tif (action->getDetails()->type == SDL_KEYDOWN)\n"
        "\t\t{\n"
        "\t\t\t_game->quit();",
        "\t\tif (action->getDetails()->type == SDL_KEYDOWN)\n"
        "\t\t{\n"
        "#ifdef __AMIGA__\n"
        "\t\t\tSDLmini_Log(\"StartState: key pressed after a load error - quitting\");\n"
        "#endif\n"
        "\t\t\t_game->quit();",
        "StartState key-quit marker")))

    results.append(("Menu/StartState.cpp (destructor markers)", edit(
        os.path.join(src, "Menu", "StartState.cpp"),
        "\tif (_thread != 0)\n"
        "\t{\n"
        "\t\tSDL_KillThread(_thread);\n"
        "\t}\n"
        "\tdelete _font;\n"
        "\tdelete _timer;\n"
        "\tdelete _lang;",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: entered\");\n"
        "#endif\n"
        "\tif (_thread != 0)\n"
        "\t{\n"
        "\t\tSDL_KillThread(_thread);\n"
        "\t}\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: thread killed\");\n"
        "#endif\n"
        "\tdelete _font;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: font deleted\");\n"
        "#endif\n"
        "\tdelete _timer;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: timer deleted\");\n"
        "#endif\n"
        "\tdelete _lang;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"~StartState: lang deleted\");\n"
        "#endif",
        "StartState destructor markers")))

    results.append(("Engine/Game.cpp (draw markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t_screen->clear();",
        "\t\t\t\tAMIGA_FRAME(\"screen clear\");\n"
        "\t\t\t\t_screen->clear();",
        "Game::run clear marker")))

    results.append(("Engine/Game.cpp (blit markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t\t(*i)->blit();",
        "\t\t\t\t\tAMIGA_FRAME(\"state blit\");\n"
        "\t\t\t\t\t(*i)->blit();\n"
        "\t\t\t\t\tAMIGA_FRAME(\"state blit done\");",
        "Game::run blit markers")))

    results.append(("Engine/Game.cpp (flip markers)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t\t\t\t_fpsCounter->blit(_screen->getSurface());\n"
        "\t\t\t\t_cursor->blit(_screen->getSurface());\n"
        "\t\t\t\t_screen->flip();",
        "\t\t\t\tAMIGA_FRAME(\"fps blit\");\n"
        "\t\t\t\t_fpsCounter->blit(_screen->getSurface());\n"
        "\t\t\t\tAMIGA_FRAME(\"cursor blit\");\n"
        "\t\t\t\t{\n"
        "\t\t\t\t\t/* AMIGA-PORT: Options::amigaCursor (Amiga tab): 1 = show the Intuition\n"
        "\t\t\t\t\t * pointer and do not blit the game cursor; 0 = as upstream. Checked\n"
        "\t\t\t\t\t * every frame so an options change takes effect at once. */\n"
        "\t\t\t\t\tstatic int pointerShown_ = -1;\n"
        "\t\t\t\t\tint want = Options::amigaCursor ? 1 : 0;\n"
        "\t\t\t\t\tif (want != pointerShown_)\n"
        "\t\t\t\t\t{\n"
        "\t\t\t\t\t\tSDL_ShowCursor(want ? SDL_ENABLE : SDL_DISABLE);\n"
        "\t\t\t\t\t\tpointerShown_ = want;\n"
        "\t\t\t\t\t}\n"
        "\t\t\t\t\tif (!want)\n"
        "\t\t\t\t\t\t_cursor->blit(_screen->getSurface());\n"
        "\t\t\t\t}\n"
        "\t\t\t\tAMIGA_FRAME(\"screen flip\");\n"
        "\t\t\t\t_screen->flip();\n"
        "\t\t\t\tAMIGA_FRAME(\"screen flip done\");",
        "Game::run flip markers")))

    results.append(("Engine/Game.cpp (include)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "#include \"Game.h\"",
        "#include \"Game.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#include <cstdio>\n"
        "#endif",
        "Game.cpp marker include")))

    # 5g. The logger reopens its file for every single line, and at verbose
    #     level echoes every line to stderr as well. On the Amiga stderr is an
    #     Intuition console window and the log lives on the host-side shared
    #     folder, so one startup meant several thousand open/append/close
    #     round trips plus several thousand lines of scrolling text - minutes
    #     of wall clock before the game did anything. The port keeps one file
    #     handle open and never writes to the console.
    results.append(("Engine/Logger.h (one open file, no console echo)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "\tFILE *file = fopen(logFile().c_str(), \"a\");\n"
        "\tif (file)\n"
        "\t{\n"
        "\t\tfprintf(file, \"%s\", ss.str().c_str());\n"
        "\t\tfflush(file);\n"
        "\t\tfclose(file);\n"
        "\t}\n"
        "\tif (!file || reportingLevel() == LOG_DEBUG || reportingLevel() == LOG_VERBOSE)\n"
        "\t{\n"
        "\t\tfprintf(stderr, \"%s\", os.str().c_str());\n"
        "\t\tfflush(stderr);\n"
        "\t}",
        "#ifdef __AMIGA__\n"
        "\tFILE *file = logHandle();\n"
        "\tif (file)\n"
        "\t{\n"
        "\t\tfprintf(file, \"%s\", ss.str().c_str());\n"
        "\t\tfflush(file);\n"
        "\t}\n"
        "#else\n"
        "\tFILE *file = fopen(logFile().c_str(), \"a\");\n"
        "\tif (file)\n"
        "\t{\n"
        "\t\tfprintf(file, \"%s\", ss.str().c_str());\n"
        "\t\tfflush(file);\n"
        "\t\tfclose(file);\n"
        "\t}\n"
        "\tif (!file || reportingLevel() == LOG_DEBUG || reportingLevel() == LOG_VERBOSE)\n"
        "\t{\n"
        "\t\tfprintf(stderr, \"%s\", os.str().c_str());\n"
        "\t\tfflush(stderr);\n"
        "\t}\n"
        "#endif",
        "logger keeps one file handle, no console echo")))

    results.append(("Engine/Logger.h (log handle)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "inline std::string& Logger::logFile()",
        "#ifdef __AMIGA__\n"
        "#include <string.h>\n"
        "/* AMIGA-PORT: one handle for the whole run instead of an open/append/\n"
        " * close per line. logFile() changes once, when Options::setFolders\n"
        " * moves the log into user/, so the name is remembered and the handle\n"
        " * reopened if it ever differs - that keeps upstream's behaviour and\n"
        " * costs one string compare per line. The handle is never closed on\n"
        " * purpose: the process exiting closes it, and every line is flushed,\n"
        " * so a crash loses nothing. */\n"
        "inline FILE* Logger::logHandle()\n"
        "{\n"
        "\t/* Plain arrays, not a std::string: a function-local static with a\n"
        "\t * constructor needs a guard variable and an atexit registration,\n"
        "\t * and this function is inline in a header that 300 translation\n"
        "\t * units include - exactly the shape the Hunk linker de-duplicates\n"
        "\t * wrongly (see the COMDAT note in CLAUDE.md). Both of these are\n"
        "\t * constant-initialised, so no guard is emitted at all. */\n"
        "\tstatic FILE* handle = 0;\n"
        "\tstatic char opened[256] = { 0 };\n"
        "\tif (handle == 0 || strncmp(opened, logFile().c_str(), sizeof(opened) - 1) != 0)\n"
        "\t{\n"
        "\t\tif (handle != 0) fclose(handle);\n"
        "\t\tstrncpy(opened, logFile().c_str(), sizeof(opened) - 1);\n"
        "\t\topened[sizeof(opened) - 1] = 0;\n"
        "\t\thandle = fopen(opened, \"w\");\n"
        "\t}\n"
        "\treturn handle;\n"
        "}\n"
        "#endif\n"
        "\n"
        "inline std::string& Logger::logFile()",
        "logger file handle accessor")))

    results.append(("Engine/Logger.h (declaration)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "\tstatic std::string& logFile();",
        "\tstatic std::string& logFile();\n"
        "#ifdef __AMIGA__\n"
        "\tstatic FILE* logHandle();   /* see the definition below */\n"
        "#endif",
        "logger file handle declaration")))

    # 5h. Logger::toString holds a function-local static array of string
    #     literals inside an inline function in a header that 300 translation
    #     units include. The Hunk linker has no COMDAT: it reports
    #     "duplicate section ...Logger8toString...buffer has DIFFERENT
    #     CONTENTS" 84 times and keeps one arbitrary copy, so the pointers in
    #     that array may belong to an object file whose rodata was dropped.
    #     Every single log line dereferences one of them. A switch over string
    #     literals needs no static object at all.
    results.append(("Engine/Logger.h (toString has no static array)", edit(
        os.path.join(src, "Engine", "Logger.h"),
        "\tstatic const char* const buffer[] = {\"FATAL\", \"ERROR\", \"WARN\", \"INFO\", \"DEBUG\", \"VERB\"};\n"
        "\treturn buffer[level];",
        "\tswitch (level)\n"
        "\t{\n"
        "\tcase LOG_FATAL:   return \"FATAL\";\n"
        "\tcase LOG_ERROR:   return \"ERROR\";\n"
        "\tcase LOG_WARNING: return \"WARN\";\n"
        "\tcase LOG_INFO:    return \"INFO\";\n"
        "\tcase LOG_DEBUG:   return \"DEBUG\";\n"
        "\tcase LOG_VERBOSE: return \"VERB\";\n"
        "\tdefault:          return \"?\";\n"
        "\t}",
        "toString without a duplicated static array")))

    results.append(("Engine/Options.cpp (include)", edit(
        os.path.join(src, "Engine", "Options.cpp"),
        "#include \"CrossPlatform.h\"",
        "#include \"CrossPlatform.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "Options::init markers include")))

    # 5z. New-game markers: the difficulty dialog's OK ends in a jump into
    #     garbage (TRAP 4); these say which of the five steps got there.
    results.append(("Menu/NewGameState.cpp (marker include)", edit(
        os.path.join(src, "Menu", "NewGameState.cpp"),
        "#include \"NewGameState.h\"",
        "#include \"NewGameState.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#endif",
        "NewGameState.cpp marker include")))
    results.append(("Menu/NewGameState.cpp (markers)", edit(
        os.path.join(src, "Menu", "NewGameState.cpp"),
        "\tSavedGame *save = _game->getMod()->newSave();\n"
        "\tsave->setDifficulty(diff);\n"
        "\tsave->setIronman(_btnIronman->getPressed());\n"
        "\t_game->setSavedGame(save);\n"
        "\n"
        "\tGeoscapeState *gs = new GeoscapeState;\n"
        "\t_game->setState(gs);\n"
        "\tgs->init();\n"
        "\t_game->pushState(new BuildNewBaseState(_game->getSavedGame()->getBases()->back(), gs->getGlobe(), true));\n",
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: OK clicked, creating save\");\n"
        "#endif\n"
        "\tSavedGame *save = _game->getMod()->newSave();\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: save created\");\n"
        "#endif\n"
        "\tsave->setDifficulty(diff);\n"
        "\tsave->setIronman(_btnIronman->getPressed());\n"
        "\t_game->setSavedGame(save);\n"
        "\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: constructing GeoscapeState\");\n"
        "#endif\n"
        "\tGeoscapeState *gs = new GeoscapeState;\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: GeoscapeState constructed\");\n"
        "#endif\n"
        "\t_game->setState(gs);\n"
        "\tgs->init();\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: GeoscapeState init done, pushing BuildNewBaseState\");\n"
        "#endif\n"
        "\t_game->pushState(new BuildNewBaseState(_game->getSavedGame()->getBases()->back(), gs->getGlobe(), true));\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_Log(\"newgame: BuildNewBaseState pushed\");\n"
        "#endif\n",
        "NewGameState markers")))

    # 5y. Missing music/sound must not be a null vtable call. With __NO_MUSIC
    #     no Music rules are ever loaded, so Mod::getMusic("GMGEO1") returns 0
    #     and GeoscapeState::init()'s music->play() jumps through address 0
    #     (TRAP 4 at PC 0xnnnn0000 - the first new-game crash). Upstream never
    #     builds without music, so it never sees this. Sound gets the same
    #     guard: a CAT with fewer entries than a ruleset expects would end the
    #     same way. Both fall back to the mute objects the Mod already owns.
    results.append(("Mod/Mod.cpp (null-safe getMusic)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\treturn getRule(name, \"Music\", _musics);\n",
        "\t\tMusic *m = getRule(name, \"Music\", _musics);\n"
        "\t\treturn m ? m : _muteMusic; /* AMIGA-PORT: no music loaded -> silence, not a jump through 0 */\n",
        "null-safe getMusic")))
    results.append(("Mod/Mod.cpp (null-safe getSound)", edit(
        os.path.join(src, "Mod", "Mod.cpp"),
        "\t\t\tSound *s = ss->getSound(sound);\n"
        "\t\t\tif (s == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tLog(LOG_ERROR) << \"Sound \" << sound << \" in \" << set << \" not found\";\n"
        "\t\t\t}\n"
        "\t\t\treturn s;\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\treturn 0;\n"
        "\t\t}\n",
        "\t\t\tSound *s = ss->getSound(sound);\n"
        "\t\t\tif (s == 0)\n"
        "\t\t\t{\n"
        "\t\t\t\tLog(LOG_ERROR) << \"Sound \" << sound << \" in \" << set << \" not found\";\n"
        "\t\t\t\ts = _muteSound; /* AMIGA-PORT: callers do getSound(..)->play() unguarded */\n"
        "\t\t\t}\n"
        "\t\t\treturn s;\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\treturn _muteSound; /* AMIGA-PORT: same */\n"
        "\t\t}\n",
        "null-safe getSound")))

    # Screen title bar: sdlmini reads SDLmini_show_bar when it opens the
    # display, so it has to be set before Screen is constructed.
    results.append(("Game.cpp (amiga app bar)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "\t// Create display\n"
        "\t_screen = new Screen();\n",
        "\t// Create display\n"
        "#ifdef __AMIGA__\n"
        "\tSDLmini_show_bar = Options::amigaAppBar ? 1 : 0;\n"
        "#endif\n"
        "\t_screen = new Screen();\n",
        "amiga app bar option")))
    results.append(("Game.cpp (amiga app bar extern)", edit(
        os.path.join(src, "Engine", "Game.cpp"),
        "#include \"Game.h\"\n",
        "#include \"Game.h\"\n"
        "#ifdef __AMIGA__\n"
        "extern \"C\" int SDLmini_show_bar; /* AMIGA-PORT: sdlmini_video.c */\n"
        "#endif\n",
        "amiga app bar extern")))

    # 5x. Globe blit diagnostics (temporary): the globe draws (first
    #     filledCircle/texturedPolygon are logged by sdlmini) but the screen
    #     stays black where it should be. Count non-zero pixels in the globe
    #     surface and in the screen after the blit, once.
    results.append(("Geoscape/Globe.cpp (marker include)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "#include \"Globe.h\"\n",
        "#include \"Globe.h\"\n"
        "#ifdef __AMIGA__\n"
        "#include \"amiga_startup.h\"\n"
        "#include <cstdio>\n"
        "extern \"C\" int SDLmini_diag_armed;\n"
        "extern \"C\" unsigned long SDLmini_flips;\n"
        "#include \"SDL_gfxPrimitives.h\"\n"
        "/* Shortest interval between two full globe redraws, milliseconds.\n"
        " * 1000 = the hard cap the port runs with; lower it once drawShadow is\n"
        " * fixed-point (PROGRESS.md) and the redraw is no longer ~330 ms. */\n"
        "#define AMIGA_GLOBE_MIN_MS 1000\n"
        "#define AMIGA_GLOBE_SUN_MINUTES 3\n"
        "#endif\n",
        "Globe.cpp marker include")))
    results.append(("Geoscape/Globe.cpp (blit markers)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "void Globe::blit(Surface *surface)\n"
        "{\n"
        "\tSurface::blit(surface);\n",
        "void Globe::blit(Surface *surface)\n"
        "{\n"
        "\tSurface::blit(surface);\n"
        "#ifdef __AMIGA__\n"
        "\t{\n"
        "\t\tstatic int once_;\n"
        "\t\tif (once_ < 3 || (once_ % 100) == 0)\n"
        "\t\t{\n"
        "\t\t\tchar b[256];\n"
        "\t\t\tlong mine = 0, theirs = 0;\n"
        "\t\t\tSDL_Surface *s = getSurface(), *t = surface->getSurface();\n"
        "\t\t\tfor (int y = 0; y < s->h; ++y) { Uint8 *p = (Uint8 *)s->pixels + y * s->pitch; for (int x = 0; x < s->w; ++x) if (p[x]) ++mine; }\n"
        "\t\t\tfor (int y = 0; y < t->h; ++y) { Uint8 *p = (Uint8 *)t->pixels + y * t->pitch; for (int x = 0; x < s->w && x < t->w; ++x) if (p[x]) ++theirs; }\n"
        "\t\t\tsnprintf(b, sizeof b, \"globe: blit #%d visible=%d hidden=%d redraw=%d at %d,%d size %dx%d pitch %d: %ld non-zero px in globe, %ld in screen area; screen %dx%d pitch %d flags %lx\",\n"
        "\t\t\t\tonce_, (int)_visible, (int)_hidden, (int)_redraw, getX(), getY(), s->w, s->h, s->pitch, mine, theirs, t->w, t->h, t->pitch, (unsigned long)s->flags);\n"
        "\t\t\tSDLmini_Log(b);\n"
        "\t\t\t{\n"
        "\t\t\t\tlong hist[256]; int k;\n"
        "\t\t\t\tfor (k = 0; k < 256; ++k) hist[k] = 0;\n"
        "\t\t\t\tfor (int y = 0; y < t->h; ++y) { Uint8 *p = (Uint8 *)t->pixels + y * t->pitch; for (int x = 0; x < s->w && x < t->w; ++x) ++hist[p[x]]; }\n"
        "\t\t\t\tint n = 0;\n"
        "\t\t\t\tn += snprintf(b + n, sizeof b - n, \"globe: screen-area histogram (idx:count rgb):\");\n"
        "\t\t\t\tfor (int r = 0; r < 8; ++r) { int best = 0; for (k = 1; k < 256; ++k) if (hist[k] > hist[best]) best = k; if (hist[best] == 0) break;\n"
        "\t\t\t\t\tSDL_Color c = t->format->palette ? t->format->palette->colors[best] : SDL_Color();\n"
        "\t\t\t\t\tn += snprintf(b + n, sizeof b - n, \" %d:%ld(%d,%d,%d)\", best, hist[best], c.r, c.g, c.b); hist[best] = 0; }\n"
        "\t\t\t\tSDLmini_Log(b);\n"
        "\t\t\t}\n"
        "\t\t\tSDLmini_diag_armed = 3;\n"
        "\t\t\t++once_;\n"
        "\t\t}\n"
        "\t}\n"
        "#endif\n",
        "Globe blit markers")))

    # 5v. State for the two globe throttles below: what _cacheLand was last
    #     projected for. Real members rather than function statics, because a
    #     new game builds a new Globe and a stale "still valid" would leave the
    #     land unprojected.
    results.append(("Geoscape/Globe.h (cache key)", edit(
        os.path.join(src, "Geoscape", "Globe.h"),
        "\tstd::list<Polygon*> _cacheLand;\n",
        "\tstd::list<Polygon*> _cacheLand;\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: what _cacheLand was projected for - see Globe::draw(). */\n"
        "\tdouble _cacheLon, _cacheLat, _cacheRadius;\n"
        "\tbool _cacheValid;\n"
        "\t/* AMIGA-PORT: what the ocean/land/shadow surface and the radar layer\n"
        "\t * currently show - see Globe::draw(). */\n"
        "\tbool _baseValid;\n"
        "\tlong _sunKey, _radarKey;\n"
        "#endif\n",
        "Globe cache key members")))

    results.append(("Geoscape/Globe.cpp (cache key init)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\t\t_randomNoiseData[i] = rand()%4;\n"
        "\n"
        "\tcachePolygons();\n"
        "}\n",
        "\t\t_randomNoiseData[i] = rand()%4;\n"
        "\n"
        "\tcachePolygons();\n"
        "#ifdef __AMIGA__\n"
        "\t_cacheLon = _cenLon;\n"
        "\t_cacheLat = _cenLat;\n"
        "\t_cacheRadius = _radius;\n"
        "\t_cacheValid = true;\n"
        "\t_baseValid = false;\n"
        "\t_sunKey = _radarKey = -1;\n"
        "#endif\n"
        "}\n",
        "Globe cache key init")))

    # 5w. Where does a globe redraw go, and does it happen every frame?
    #     `SDLmini_flips` is one per rendered frame, so "10 draws over N frames"
    #     answers the second question outright; the per-phase millisecond sums
    #     answer the first. drawShadow is double-precision maths per pixel and
    #     goes through the ROM IEEE library, so it is the prime suspect.
    results.append(("Geoscape/Globe.cpp (draw timing)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "void Globe::draw()\n"
        "{\n"
        "\tif (_redraw)\n"
        "\t{\n"
        "\t\tcachePolygons();\n"
        "\t}\n"
        "\tSurface::draw();\n"
        "\tdrawOcean();\n"
        "\tdrawLand();\n"
        "\tdrawRadars();\n"
        "\tdrawShadow();\n"
        "\tdrawMarkers();\n"
        "\tdrawDetail();\n"
        "\tdrawFlights();\n"
        "}\n",
        "void Globe::draw()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: draw only what changed. Upstream repaints the whole globe\n"
        "\t * (ocean, land, day/night shadow, radars, countries, markers) on every\n"
        "\t * clock tick - 10 times a second at the slowest speed - because on a PC\n"
        "\t * that is free. Here a full repaint is ~150 ms on an 040/40, so the\n"
        "\t * geoscape ran at 3-4 fps with nobody touching anything.\n"
        "\t *   - ocean+land+shadow (this surface): only when the projection changed\n"
        "\t *     (rotate/zoom) or the sun moved far enough to shift the terminator\n"
        "\t *     by about a pixel (AMIGA_GLOBE_SUN_MINUTES of game time), and never\n"
        "\t *     more often than once per AMIGA_GLOBE_MIN_MS;\n"
        "\t *   - radars+flight paths (_radars): with the base, or when the hover\n"
        "\t *     circle / base count / craft count changed;\n"
        "\t *   - countries/cities (_countries): with the base (projection only);\n"
        "\t *   - markers (_markers): every call, they are cheap and things move.\n"
        "\t * Nothing else is touched, so a quiet globe costs the markers only. */\n"
        "\tstatic unsigned long calls_ = 0, lastFlips_ = 0, baseDraws_ = 0, radarDraws_ = 0;\n"
        "\tstatic Uint32 lastTicks_ = 0, lastBase_ = 0, sBase = 0, sCache = 0, sRadar = 0, sMark = 0, sDetail = 0;\n"
        "\t++calls_;\n"
        "\t_redraw = false;\n"
        "\n"
        "\tconst GameTime *gt = _game->getSavedGame()->getTime();\n"
        "\tconst long sunKey = ((((long)gt->getMonth() * 32 + gt->getDay()) * 24 + gt->getHour()) * 60 + gt->getMinute()) / AMIGA_GLOBE_SUN_MINUTES;\n"
        "\tconst bool proj = (!_cacheValid || _cacheLon != _cenLon || _cacheLat != _cenLat || _cacheRadius != _radius);\n"
        "\tlong radarKey = (long)_game->getSavedGame()->getBases()->size() * 100000L;\n"
        "\tif (_hover)\n"
        "\t\tradarKey += 50000L + (long)(_hoverLon * 1000.0) * 7L + (long)(_hoverLat * 1000.0) * 13L;\n"
        "\tfor (std::vector<Base*>::iterator bi = _game->getSavedGame()->getBases()->begin(); bi != _game->getSavedGame()->getBases()->end(); ++bi)\n"
        "\t\tfor (std::vector<Craft*>::iterator ci = (*bi)->getCrafts()->begin(); ci != (*bi)->getCrafts()->end(); ++ci)\n"
        "\t\t{\n"
        "\t\t\tradarKey += 1;\n"
        "\t\t\tif ((*ci)->getStatus() == \"STR_OUT\")\n"
        "\t\t\t\tradarKey += 1000L + sunKey * 17L; /* flight paths and craft radars move: refresh with the sun key */\n"
        "\t\t}\n"
        "\n"
        "\tconst Uint32 now = SDL_GetTicks();\n"
        "\tbool wantBase = (!_baseValid || proj || sunKey != _sunKey);\n"
        "\tif (wantBase && _baseValid && lastBase_ != 0 && (Uint32)(now - lastBase_) < AMIGA_GLOBE_MIN_MS)\n"
        "\t{\n"
        "\t\t/* throttled: keep showing the previous image; the next call retries.\n"
        "\t\t * If the projection moved, the layers on top would not line up with\n"
        "\t\t * the old base, so leave them alone as well. */\n"
        "\t\tif (proj)\n"
        "\t\t\treturn;\n"
        "\t\twantBase = false;\n"
        "\t}\n"
        "\tif (wantBase)\n"
        "\t{\n"
        "\t\tUint32 t0 = SDL_GetTicks();\n"
        "\t\tif (proj)\n"
        "\t\t{\n"
        "\t\t\tcachePolygons();\n"
        "\t\t\t_cacheLon = _cenLon;\n"
        "\t\t\t_cacheLat = _cenLat;\n"
        "\t\t\t_cacheRadius = _radius;\n"
        "\t\t\t_cacheValid = true;\n"
        "\t\t}\n"
        "\t\tUint32 t1 = SDL_GetTicks();\n"
        "\t\tSurface::draw();\n"
        "\t\tdrawOcean();\n"
        "\t\tdrawLand();\n"
        "\t\tdrawShadow();\n"
        "\t\tUint32 t2 = SDL_GetTicks();\n"
        "\t\tdrawDetail();\n"
        "\t\tsCache += t1 - t0; sBase += t2 - t1; sDetail += SDL_GetTicks() - t2;\n"
        "\t\t++baseDraws_;\n"
        "\t\t_baseValid = true;\n"
        "\t\t_sunKey = sunKey;\n"
        "\t\tlastBase_ = now;\n"
        "\t}\n"
        "\tif (wantBase || radarKey != _radarKey)\n"
        "\t{\n"
        "\t\tUint32 t0 = SDL_GetTicks();\n"
        "\t\tdrawRadars();\n"
        "\t\tdrawFlights();\n"
        "\t\tsRadar += SDL_GetTicks() - t0;\n"
        "\t\t++radarDraws_;\n"
        "\t\t_radarKey = radarKey;\n"
        "\t}\n"
        "\t{\n"
        "\t\tUint32 t0 = SDL_GetTicks();\n"
        "\t\tdrawMarkers();\n"
        "\t\tsMark += SDL_GetTicks() - t0;\n"
        "\t}\n"
        "\tif ((calls_ % 50) == 0)\n"
        "\t{\n"
        "\t\tchar b[200];\n"
        "\t\tsnprintf(b, sizeof b, \"globe: 50 calls in %lu ms over %lu frames: base %lu (cache %lu + draw %lu + detail %lu ms each), radar %lu (%lu ms each), markers %lu ms total\",\n"
        "\t\t\t(unsigned long)(now - lastTicks_), SDLmini_flips - lastFlips_,\n"
        "\t\t\tbaseDraws_, baseDraws_ ? (unsigned long)sCache / baseDraws_ : 0UL, baseDraws_ ? (unsigned long)sBase / baseDraws_ : 0UL, baseDraws_ ? (unsigned long)sDetail / baseDraws_ : 0UL,\n"
        "\t\t\tradarDraws_, radarDraws_ ? (unsigned long)sRadar / radarDraws_ : 0UL, (unsigned long)sMark);\n"
        "\t\tSDLmini_Log(b);\n"
        "\t\tlastTicks_ = now; lastFlips_ = SDLmini_flips;\n"
        "\t\tbaseDraws_ = radarDraws_ = 0; sBase = sCache = sRadar = sMark = sDetail = 0;\n"
        "\t}\n"
        "#else\n"
        "\tif (_redraw)\n"
        "\t{\n"
        "\t\tcachePolygons();\n"
        "\t}\n"
        "\tSurface::draw();\n"
        "\tdrawOcean();\n"
        "\tdrawLand();\n"
        "\tdrawRadars();\n"
        "\tdrawShadow();\n"
        "\tdrawMarkers();\n"
        "\tdrawDetail();\n"
        "\tdrawFlights();\n"
        "#endif\n"
        "}\n",
        "Globe draw timing")))

    # 5u. drawShadow in fixed point. Measured without JIT (PROGRESS.md): a globe
    #     redraw was ~330 ms, ~280 of them in drawShadow, whose per-pixel loop
    #     made 26 calls into the ROM IEEE double library. The maths is a squared
    #     distance between two unit vectors, a scale, a clamp and a table
    #     lookup - all integer work in Q1.14:
    #       - `CordFix` (Globe.h): three Sint16 components, 6 bytes per pixel
    #         instead of Cord's 24. _earthFix replaces _earthData for the
    #         shader (256x200 x 6 zoom levels: 7.4 MB of doubles -> 1.8 MB).
    #       - `CreateShadowFix` (Globe.cpp): the same decision tree as
    #         CreateShadow with the double arithmetic replaced. Products of two
    #         Q14 differences are Q28 and up to 2^30 each, so each is dropped to
    #         Q24 before summing (max 3*2^26, fits); the "-2, *125" step is done
    #         in Q16 so *125 cannot overflow; the gradient index uses C division
    #         (truncation toward zero) exactly like the original (Sint16) cast.
    #       - z is stored as at least 1 inside the disc, so a rim pixel whose
    #         real z rounds to 0 is still shaded, not blacked out ("earth.z"
    #         doubles as the inside-the-disc test in func()).
    #     CreateShadow (double) stays for the one call per query in
    #     getPolygonTextureAndShade; getSunDirection stays double - once per
    #     redraw, not per pixel.
    results.append(("Geoscape/Globe.h (CordFix)", edit(
        os.path.join(src, "Geoscape", "Globe.h"),
        "class Globe : public InteractiveSurface\n",
        "#ifdef __AMIGA__\n"
        "/* AMIGA-PORT: a unit vector in Q1.14 - what the day/night shader reads per\n"
        " * pixel. See CreateShadowFix in Globe.cpp. */\n"
        "struct CordFix\n"
        "{\n"
        "\tSint16 x, y, z;\n"
        "};\n"
        "#endif\n"
        "\n"
        "class Globe : public InteractiveSurface\n",
        "CordFix type")))
    results.append(("Geoscape/Globe.h (earthFix member)", edit(
        os.path.join(src, "Geoscape", "Globe.h"),
        "\tstd::vector<std::vector<Cord> > _earthData;\n",
        "\tstd::vector<std::vector<Cord> > _earthData;\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: the same normals in Q1.14; _earthData is left empty. */\n"
        "\tstd::vector<std::vector<CordFix> > _earthFix;\n"
        "#endif\n",
        "earthFix member")))
    results.append(("Geoscape/Globe.cpp (CreateShadowFix)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\tstatic inline void func(Uint8& dest, const Cord& earth, const Cord& sun, const Sint16& noise, const int&)\n"
        "\t{\n"
        "\t\tif (dest && earth.z)\n"
        "\t\t\tdest = getShadowValue(dest, earth, sun, noise);\n"
        "\t\telse\n"
        "\t\t\tdest = 0;\n"
        "\t}\n"
        "};\n",
        "\tstatic inline void func(Uint8& dest, const Cord& earth, const Cord& sun, const Sint16& noise, const int&)\n"
        "\t{\n"
        "\t\tif (dest && earth.z)\n"
        "\t\t\tdest = getShadowValue(dest, earth, sun, noise);\n"
        "\t\telse\n"
        "\t\t\tdest = 0;\n"
        "\t}\n"
        "};\n"
        "\n"
        "#ifdef __AMIGA__\n"
        "/* AMIGA-PORT: CreateShadow with the arithmetic in Q1.14 integers. Same\n"
        " * decisions, same table, same palette logic; only the double maths is\n"
        " * gone. On a 68020 without FPU every double operation in the original\n"
        " * was a call into the Kickstart IEEE library - 26 of them per pixel. */\n"
        "struct CreateShadowFix\n"
        "{\n"
        "\tstatic inline Uint8 getShadowValue(const Uint8& dest, const CordFix& earth, const CordFix& sun, const Sint16& noise)\n"
        "\t{\n"
        "\t\tconst Sint32 dx = (Sint32)earth.x - sun.x;   /* Q14, |d| <= 2 */\n"
        "\t\tconst Sint32 dy = (Sint32)earth.y - sun.y;\n"
        "\t\tconst Sint32 dz = (Sint32)earth.z - sun.z;\n"
        "\t\t/* squared distance: Q28 products dropped to Q24 before the sum */\n"
        "\t\tconst Sint32 n = ((dx * dx) >> 4) + ((dy * dy) >> 4) + ((dz * dz) >> 4);\n"
        "\t\t/* (n - 2) * 125, kept in Q16 */\n"
        "\t\tconst Sint32 x = ((n - (2L << 24)) >> 8) * 125;\n"
        "\t\tint v;\n"
        "\t\tif (x < -(110L << 16))\n"
        "\t\t\tv = -31;\n"
        "\t\telse if (x > (120L << 16))\n"
        "\t\t\tv = 50;\n"
        "\t\telse\n"
        "\t\t\tv = static_data.shade_gradient[(int)(x / 65536) + 120];\n"
        "\n"
        "\t\tv -= noise;\n"
        "\n"
        "\t\tif (v > 0)\n"
        "\t\t{\n"
        "\t\t\tconst int val = (v > 31) ? 31 : v;\n"
        "\t\t\tconst int d = dest & helper::ColorGroup;\n"
        "\t\t\tif (d == Globe::OCEAN_COLOR || d == Globe::OCEAN_COLOR + 16)\n"
        "\t\t\t{\n"
        "\t\t\t\treturn Globe::OCEAN_COLOR + val;\n"
        "\t\t\t}\n"
        "\t\t\telse\n"
        "\t\t\t{\n"
        "\t\t\t\tif (dest == 0) return val;\n"
        "\t\t\t\tconst int s = val / 3;\n"
        "\t\t\t\tconst int e = dest + s;\n"
        "\t\t\t\tif (e > d + helper::ColorShade)\n"
        "\t\t\t\t\treturn d + helper::ColorShade;\n"
        "\t\t\t\treturn e;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\telse\n"
        "\t\t{\n"
        "\t\t\tconst int d = dest & helper::ColorGroup;\n"
        "\t\t\tif (d == Globe::OCEAN_COLOR || d == Globe::OCEAN_COLOR + 16)\n"
        "\t\t\t\treturn Globe::OCEAN_COLOR;\n"
        "\t\t\telse\n"
        "\t\t\t\treturn dest;\n"
        "\t\t}\n"
        "\t}\n"
        "\n"
        "\tstatic inline void func(Uint8& dest, const CordFix& earth, const CordFix& sun, const Sint16& noise, const int&)\n"
        "\t{\n"
        "\t\tif (dest && earth.z)\n"
        "\t\t\tdest = getShadowValue(dest, earth, sun, noise);\n"
        "\t\telse\n"
        "\t\t\tdest = 0;\n"
        "\t}\n"
        "};\n"
        "\n"
        "/* double unit vector -> Q1.14, rounded */\n"
        "static inline CordFix cordToFix(const Cord &c)\n"
        "{\n"
        "\tCordFix f;\n"
        "\tf.x = (Sint16)floor(c.x * 16384.0 + 0.5);\n"
        "\tf.y = (Sint16)floor(c.y * 16384.0 + 0.5);\n"
        "\tf.z = (Sint16)floor(c.z * 16384.0 + 0.5);\n"
        "\treturn f;\n"
        "}\n"
        "#endif\n",
        "CreateShadowFix shader")))
    results.append(("Geoscape/Globe.cpp (earthFix fill)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "\tfor (size_t r = 0; r<_zoomRadius.size(); ++r)\n"
        "\t{\n"
        "\t\t_earthData[r].resize(width * height);\n"
        "\t\tfor (int j=0; j<height; ++j)\n"
        "\t\t\tfor (int i=0; i<width; ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\t_earthData[r][width*j + i] = static_data.circle_norm(width/2, height/2, _zoomRadius[r], i+.5, j+.5);\n"
        "\t\t\t}\n"
        "\t}\n",
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: the normals go straight into Q1.14; the double table is\n"
        "\t * never allocated (it would be 7.4 MB). Inside the disc z is kept >= 1\n"
        "\t * so the shader's inside test never loses a rim pixel to rounding. */\n"
        "\t_earthFix.resize(_zoomRadius.size());\n"
        "\tfor (size_t r = 0; r<_zoomRadius.size(); ++r)\n"
        "\t{\n"
        "\t\t_earthFix[r].resize(width * height);\n"
        "\t\tfor (int j=0; j<height; ++j)\n"
        "\t\t\tfor (int i=0; i<width; ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\tCord c = static_data.circle_norm(width/2, height/2, _zoomRadius[r], i+.5, j+.5);\n"
        "\t\t\t\tCordFix f = cordToFix(c);\n"
        "\t\t\t\tif (c.z != 0. && f.z == 0) f.z = 1;\n"
        "\t\t\t\t_earthFix[r][width*j + i] = f;\n"
        "\t\t\t}\n"
        "\t}\n"
        "#else\n"
        "\tfor (size_t r = 0; r<_zoomRadius.size(); ++r)\n"
        "\t{\n"
        "\t\t_earthData[r].resize(width * height);\n"
        "\t\tfor (int j=0; j<height; ++j)\n"
        "\t\t\tfor (int i=0; i<width; ++i)\n"
        "\t\t\t{\n"
        "\t\t\t\t_earthData[r][width*j + i] = static_data.circle_norm(width/2, height/2, _zoomRadius[r], i+.5, j+.5);\n"
        "\t\t\t}\n"
        "\t}\n"
        "#endif\n",
        "earthFix fill")))
    results.append(("Geoscape/Globe.cpp (fixed-point drawShadow)", edit(
        os.path.join(src, "Geoscape", "Globe.cpp"),
        "void Globe::drawShadow()\n"
        "{\n"
        "\tShaderMove<Cord> earth = ShaderMove<Cord>(_earthData[_zoom], getWidth(), getHeight());\n"
        "\tShaderRepeat<Sint16> noise = ShaderRepeat<Sint16>(_randomNoiseData, static_data.random_surf_size, static_data.random_surf_size);\n"
        "\n"
        "\tearth.setMove(_cenX-getWidth()/2, _cenY-getHeight()/2);\n"
        "\n"
        "\tlock();\n"
        "\tShaderDraw<CreateShadow>(ShaderSurface(this), earth, ShaderScalar(getSunDirection(_cenLon, _cenLat)), noise);\n"
        "\tunlock();\n",
        "void Globe::drawShadow()\n"
        "{\n"
        "#ifdef __AMIGA__\n"
        "\t/* AMIGA-PORT: fixed-point shader; see CreateShadowFix. */\n"
        "\tShaderMove<CordFix> earth = ShaderMove<CordFix>(_earthFix[_zoom], getWidth(), getHeight());\n"
        "\tShaderRepeat<Sint16> noise = ShaderRepeat<Sint16>(_randomNoiseData, static_data.random_surf_size, static_data.random_surf_size);\n"
        "\n"
        "\tearth.setMove(_cenX-getWidth()/2, _cenY-getHeight()/2);\n"
        "\n"
        "\tCordFix sun = cordToFix(getSunDirection(_cenLon, _cenLat));\n"
        "\tlock();\n"
        "\tShaderDraw<CreateShadowFix>(ShaderSurface(this), earth, ShaderScalar(sun), noise);\n"
        "\tunlock();\n"
        "#else\n"
        "\tShaderMove<Cord> earth = ShaderMove<Cord>(_earthData[_zoom], getWidth(), getHeight());\n"
        "\tShaderRepeat<Sint16> noise = ShaderRepeat<Sint16>(_randomNoiseData, static_data.random_surf_size, static_data.random_surf_size);\n"
        "\n"
        "\tearth.setMove(_cenX-getWidth()/2, _cenY-getHeight()/2);\n"
        "\n"
        "\tlock();\n"
        "\tShaderDraw<CreateShadow>(ShaderSurface(this), earth, ShaderScalar(getSunDirection(_cenLon, _cenLat)), noise);\n"
        "\tunlock();\n"
        "#endif\n",
        "fixed-point drawShadow")))

    # 6. File streams. bebbo's libstdc++ hangs forever in
    #    std::ifstream::close() on a file that exists (see native/amiga_fstream.h
    #    for the proof), and every destructor calls close(). Every use in the
    #    game is switched to the stdio-backed replacements, which behave the
    #    same way from the caller's point of view.
    swapped = []
    for root, _dirs, files in os.walk(src):
        for fn in files:
            if not fn.endswith((".cpp", ".h")):
                continue
            path = os.path.join(root, fn)
            with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
                text = f.read()
            if "std::ifstream" not in text and "std::ofstream" not in text:
                continue
            text = text.replace("std::ifstream", "OpenXcom::AmigaIFStream")
            text = text.replace("std::ofstream", "OpenXcom::AmigaOFStream")
            if '#include "amiga_fstream.h"' not in text:
                # after the first #include in the file, so it lands past the
                # licence header and any #pragma once
                idx = text.find("#include")
                end = text.find("\n", idx)
                text = text[:end + 1] + '#include "amiga_fstream.h"\n' + text[end + 1:]
            with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
                f.write(text)
            swapped.append(os.path.relpath(path, src))
    results.append(("file streams", "%d files" % len(swapped) if swapped else "already"))

    for name, state in results:
        print("  %-24s %s" % (name, state))


if __name__ == "__main__":
    main()
