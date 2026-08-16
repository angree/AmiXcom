/*
 * AMIGA-PORT: the "Amiga" options tab (first tab of the options screen).
 *
 *   Amiga screen title bar  off / on   -> Options::amigaAppBar
 *   Mouse pointer           original / Amiga only -> Options::amigaCursor
 *
 * The strings are in bin/common/Language/en-US.yml (added by the patch
 * script). The interface colours reuse "videoMenu" so no ruleset change is
 * needed. Layout follows OptionsAudioState.
 */
#include "OptionsAmigaState.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Action.h"
#include "../Engine/Options.h"
#include "../Interface/ComboBox.h"
#include "../Interface/Text.h"

namespace OpenXcom
{

OptionsAmigaState::OptionsAmigaState(OptionsOrigin origin) : OptionsBaseState(origin)
{
	setCategory(_btnAmiga);

	_txtAppBar = new Text(218, 9, 94, 8);
	_cbxAppBar = new ComboBox(this, 104, 16, 94, 18);

	_txtCursor = new Text(218, 9, 94, 40);
	_cbxCursor = new ComboBox(this, 104, 16, 94, 50);

	add(_txtAppBar, "text", "videoMenu");
	add(_txtCursor, "text", "videoMenu");
	add(_cbxCursor, "button", "videoMenu");
	add(_cbxAppBar, "button", "videoMenu");

	centerAllSurfaces();

	std::vector<std::wstring> onOff, cursors;
	onOff.push_back(tr("STR_AMIGA_OFF"));
	onOff.push_back(tr("STR_AMIGA_ON"));
	cursors.push_back(tr("STR_AMIGA_CURSOR_ORIGINAL"));
	cursors.push_back(tr("STR_AMIGA_CURSOR_AMIGA"));

	_txtAppBar->setText(tr("STR_AMIGA_APP_BAR"));
	_cbxAppBar->setOptions(onOff);
	_cbxAppBar->setSelected(Options::amigaAppBar ? 1 : 0);
	_cbxAppBar->onChange((ActionHandler)&OptionsAmigaState::cbxAppBarChange);
	_cbxAppBar->setTooltip("STR_AMIGA_APP_BAR_DESC");
	_cbxAppBar->onMouseIn((ActionHandler)&OptionsAmigaState::txtTooltipIn);
	_cbxAppBar->onMouseOut((ActionHandler)&OptionsAmigaState::txtTooltipOut);

	_txtCursor->setText(tr("STR_AMIGA_CURSOR"));
	_cbxCursor->setOptions(cursors);
	_cbxCursor->setSelected(Options::amigaCursor ? 1 : 0);
	_cbxCursor->onChange((ActionHandler)&OptionsAmigaState::cbxCursorChange);
	_cbxCursor->setTooltip("STR_AMIGA_CURSOR_DESC");
	_cbxCursor->onMouseIn((ActionHandler)&OptionsAmigaState::txtTooltipIn);
	_cbxCursor->onMouseOut((ActionHandler)&OptionsAmigaState::txtTooltipOut);
}

OptionsAmigaState::~OptionsAmigaState()
{
}

void OptionsAmigaState::cbxAppBarChange(Action *)
{
	Options::amigaAppBar = (_cbxAppBar->getSelected() == 1);
}

void OptionsAmigaState::cbxCursorChange(Action *)
{
	Options::amigaCursor = (int)_cbxCursor->getSelected();
}

}
