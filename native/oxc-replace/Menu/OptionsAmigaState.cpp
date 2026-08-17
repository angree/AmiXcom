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

	_txtFov = new Text(218, 9, 94, 72);
	_cbxFov = new ComboBox(this, 104, 16, 94, 82);

	_txtAnim = new Text(218, 9, 94, 104);
	_cbxAnim = new ComboBox(this, 104, 16, 94, 114);

	add(_txtAppBar, "text", "videoMenu");
	add(_txtCursor, "text", "videoMenu");
	add(_txtFov, "text", "videoMenu");
	add(_txtAnim, "text", "videoMenu");
	add(_cbxAnim, "button", "videoMenu");
	add(_cbxFov, "button", "videoMenu");
	add(_cbxCursor, "button", "videoMenu");
	add(_cbxAppBar, "button", "videoMenu");

	centerAllSurfaces();

	std::vector<std::wstring> onOff, cursors, fovs, anims;
	onOff.push_back(tr("STR_AMIGA_OFF"));
	onOff.push_back(tr("STR_AMIGA_ON"));
	cursors.push_back(tr("STR_AMIGA_CURSOR_ORIGINAL"));
	cursors.push_back(tr("STR_AMIGA_CURSOR_AMIGA"));
	fovs.push_back(tr("STR_AMIGA_FOV_FAST"));
	fovs.push_back(tr("STR_AMIGA_FOV_ACCURATE"));
	fovs.push_back(tr("STR_AMIGA_FOV_TEST"));
	anims.push_back(tr("STR_AMIGA_ANIM_NORMAL"));
	anims.push_back(tr("STR_AMIGA_ANIM_HALF"));

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

	_txtFov->setText(tr("STR_AMIGA_FOV"));
	_cbxFov->setOptions(fovs);
	_cbxFov->setSelected((size_t)Options::amigaAccurateFov);
	_cbxFov->onChange((ActionHandler)&OptionsAmigaState::cbxFovChange);
	_cbxFov->setTooltip("STR_AMIGA_FOV_DESC");
	_cbxFov->onMouseIn((ActionHandler)&OptionsAmigaState::txtTooltipIn);
	_cbxFov->onMouseOut((ActionHandler)&OptionsAmigaState::txtTooltipOut);

	_txtAnim->setText(tr("STR_AMIGA_ANIM"));
	_cbxAnim->setOptions(anims);
	_cbxAnim->setSelected(Options::amigaAnimMs >= 200 ? 1 : 0);
	_cbxAnim->onChange((ActionHandler)&OptionsAmigaState::cbxAnimChange);
	_cbxAnim->setTooltip("STR_AMIGA_ANIM_DESC");
	_cbxAnim->onMouseIn((ActionHandler)&OptionsAmigaState::txtTooltipIn);
	_cbxAnim->onMouseOut((ActionHandler)&OptionsAmigaState::txtTooltipOut);
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

void OptionsAmigaState::cbxFovChange(Action *)
{
	Options::amigaAccurateFov = (int)_cbxFov->getSelected();
}

void OptionsAmigaState::cbxAnimChange(Action *)
{
	Options::amigaAnimMs = _cbxAnim->getSelected() == 1 ? 200 : 100;
}

}
