/*
 * AMIGA-PORT: the "Amiga" options tab (first tab of the options screen).
 *
 * A scrolling TextList in the style of the ADVANCED tab: one row per
 * option, left click cycles the value forward, right click backward, and
 * the row's description shows in the shared tooltip area at the bottom.
 * The strings are in bin/common/Language/en-US.yml (added by the patch
 * script). The interface colours reuse "videoMenu".
 *
 * Rows:
 *   Amiga screen title bar        Off / On            Options::amigaAppBar
 *   Mouse pointer                 Original / Amiga    Options::amigaCursor
 *   Map reveal                    Fast/Accurate/Test  Options::amigaAccurateFov
 *   Battle animation speed        Normal / Half       Options::amigaAnimMs
 *   Split movement calculation    Off / On            Options::amigaSplitWalk
 *   Display standard              Auto/PAL/NTSC       Options::amigaVideoMode
 *   Language from Workbench       Off / On            Options::amigaLangAuto
 */
#include "OptionsAmigaState.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Action.h"
#include "../Engine/Options.h"
#include "../Interface/TextList.h"
#include "../Interface/Text.h"
#include "../Interface/Window.h"

namespace OpenXcom
{

enum
{
	AMIGA_ROW_APPBAR = 0,
	AMIGA_ROW_CURSOR,
	AMIGA_ROW_FOV,
	AMIGA_ROW_ANIM,
	AMIGA_ROW_SPLITWALK,
	AMIGA_ROW_MUSIC,
	AMIGA_ROW_MUSICQ,
	AMIGA_ROW_VIDEO,
	AMIGA_ROW_LANGAUTO,
	AMIGA_ROW_COUNT
};

static const char *amigaRowLabel_[AMIGA_ROW_COUNT] =
{
	"STR_AMIGA_APP_BAR",
	"STR_AMIGA_CURSOR",
	"STR_AMIGA_FOV",
	"STR_AMIGA_ANIM",
	"STR_AMIGA_SPLIT_WALK",
	"STR_AMIGA_MUSIC",
	"STR_AMIGA_MUSIC_QUALITY",
	"STR_AMIGA_VIDEO",
	"STR_AMIGA_LANG_AUTO"
};

static const char *amigaRowDesc_[AMIGA_ROW_COUNT] =
{
	"STR_AMIGA_APP_BAR_DESC",
	"STR_AMIGA_CURSOR_DESC",
	"STR_AMIGA_FOV_DESC",
	"STR_AMIGA_ANIM_DESC",
	"STR_AMIGA_SPLIT_WALK_DESC",
	"STR_AMIGA_MUSIC_DESC",
	"STR_AMIGA_MUSIC_QUALITY_DESC",
	"STR_AMIGA_VIDEO_DESC",
	"STR_AMIGA_LANG_AUTO_DESC"
};

/* how many values each row cycles through */
static const int amigaRowVals_[AMIGA_ROW_COUNT] = { 2, 2, 3, 2, 2, 3, 2, 3, 2 };

/* pre-rendered music always renders at high quality: the switch is dead */
static bool amigaRowDisabled_(size_t row)
{
	return row == AMIGA_ROW_MUSICQ && Options::amigaMusic == 2;
}

static int amigaRowGet_(size_t row)
{
	switch (row)
	{
	case AMIGA_ROW_APPBAR:    return Options::amigaAppBar ? 1 : 0;
	case AMIGA_ROW_CURSOR:    return Options::amigaCursor ? 1 : 0;
	case AMIGA_ROW_FOV:       return Options::amigaAccurateFov;
	case AMIGA_ROW_ANIM:      return Options::amigaAnimMs >= 200 ? 1 : 0;
	case AMIGA_ROW_SPLITWALK: return Options::amigaSplitWalk ? 1 : 0;
	case AMIGA_ROW_MUSIC:     return Options::amigaMusic;
	case AMIGA_ROW_MUSICQ:    return Options::amigaMusicQuality ? 1 : 0;
	case AMIGA_ROW_VIDEO:     return Options::amigaVideoMode;
	case AMIGA_ROW_LANGAUTO:  return Options::amigaLangAuto ? 1 : 0;
	}
	return 0;
}

static void amigaRowSet_(size_t row, int v)
{
	switch (row)
	{
	case AMIGA_ROW_APPBAR:    Options::amigaAppBar = (v == 1); break;
	case AMIGA_ROW_CURSOR:    Options::amigaCursor = v; break;
	case AMIGA_ROW_FOV:       Options::amigaAccurateFov = v; break;
	case AMIGA_ROW_ANIM:      Options::amigaAnimMs = (v == 1) ? 200 : 100; break;
	case AMIGA_ROW_SPLITWALK: Options::amigaSplitWalk = (v == 1); break;
	case AMIGA_ROW_MUSIC:     Options::amigaMusic = v; break;
	case AMIGA_ROW_MUSICQ:    Options::amigaMusicQuality = v; break;
	/* Only stored here. The screen is reopened on the way out of the
	 * options screen (Screen::resetDisplay -> SDL_SetVideoMode), never
	 * while the row is being cycled. */
	case AMIGA_ROW_VIDEO:     Options::amigaVideoMode = v; break;
	/* Takes effect at the next start, like the display standard: the
	 * language is chosen while the game is loading its data. */
	case AMIGA_ROW_LANGAUTO:  Options::amigaLangAuto = (v == 1); break;
	}
}

static const char *amigaRowValue_(size_t row, int v)
{
	switch (row)
	{
	case AMIGA_ROW_CURSOR:
		return v == 1 ? "STR_AMIGA_CURSOR_AMIGA" : "STR_AMIGA_CURSOR_ORIGINAL";
	case AMIGA_ROW_FOV:
		return v == 2 ? "STR_AMIGA_FOV_TEST" : (v == 1 ? "STR_AMIGA_FOV_ACCURATE" : "STR_AMIGA_FOV_FAST");
	case AMIGA_ROW_ANIM:
		return v == 1 ? "STR_AMIGA_ANIM_HALF" : "STR_AMIGA_ANIM_NORMAL";
	case AMIGA_ROW_MUSIC:
		return v == 2 ? "STR_AMIGA_MUSIC_PRE"
		     : (v == 1 ? "STR_AMIGA_MUSIC_LIVE" : "STR_AMIGA_MUSIC_OFF");
	case AMIGA_ROW_MUSICQ:
		return v == 1 ? "STR_AMIGA_QUALITY_HIGH" : "STR_AMIGA_QUALITY_LOW";
	case AMIGA_ROW_VIDEO:
		return v == 2 ? "STR_AMIGA_VIDEO_NTSC"
		     : (v == 1 ? "STR_AMIGA_VIDEO_PAL" : "STR_AMIGA_VIDEO_AUTO");
	default:
		return v == 1 ? "STR_AMIGA_ON" : "STR_AMIGA_OFF";
	}
}

OptionsAmigaState::OptionsAmigaState(OptionsOrigin origin) : OptionsBaseState(origin)
{
	setCategory(_btnAmiga);

	_lstOptions = new TextList(200, 136, 94, 8);
	add(_lstOptions, "optionLists", "advancedMenu");

	centerAllSurfaces();

	_lstOptions->setColumns(2, 168, 32);
	_lstOptions->setWordWrap(true);
	_lstOptions->setSelectable(true);
	_lstOptions->setBackground(_window);
	_lstOptions->onMouseClick((ActionHandler)&OptionsAmigaState::lstOptionsClick, 0);
	_lstOptions->onMouseOver((ActionHandler)&OptionsAmigaState::lstOptionsMouseOver);
	_lstOptions->onMouseOut((ActionHandler)&OptionsAmigaState::lstOptionsMouseOut);

	for (size_t row = 0; row < AMIGA_ROW_COUNT; ++row)
	{
		_lstOptions->addRow(2, tr(amigaRowLabel_[row]).c_str(),
			tr(amigaRowValue_(row, amigaRowGet_(row))).c_str());
		if (amigaRowDisabled_(row))
		{
			_lstOptions->setRowColor(row, _lstOptions->getSecondaryColor());
		}
	}
}

OptionsAmigaState::~OptionsAmigaState()
{
}

void OptionsAmigaState::updateRow(size_t row)
{
	_lstOptions->setCellText(row, 1, tr(amigaRowValue_(row, amigaRowGet_(row))));
	_lstOptions->setRowColor(row, amigaRowDisabled_(row)
		? _lstOptions->getSecondaryColor() : _lstOptions->getColor());
}

void OptionsAmigaState::lstOptionsClick(Action *action)
{
	Uint8 button = action->getDetails()->button.button;
	if (button != SDL_BUTTON_LEFT && button != SDL_BUTTON_RIGHT)
	{
		return;
	}
	size_t row = _lstOptions->getSelectedRow();
	if (row >= AMIGA_ROW_COUNT)
	{
		return;
	}
	if (amigaRowDisabled_(row))
	{
		return;
	}
	const int n = amigaRowVals_[row];
	int v = amigaRowGet_(row);
	if (button == SDL_BUTTON_LEFT)
		v = (v + 1) % n;
	else
		v = (v + n - 1) % n;
	amigaRowSet_(row, v);
	updateRow(row);
	if (row == AMIGA_ROW_MUSIC)
	{
		updateRow(AMIGA_ROW_MUSICQ);   /* greys out for pre-rendered music */
	}
}

void OptionsAmigaState::lstOptionsMouseOver(Action *)
{
	size_t row = _lstOptions->getSelectedRow();
	std::wstring desc;
	if (row < AMIGA_ROW_COUNT)
	{
		desc = tr(amigaRowDesc_[row]);
	}
	_txtTooltip->setText(desc);
}

void OptionsAmigaState::lstOptionsMouseOut(Action *)
{
	_txtTooltip->setText(L"");
}

}
