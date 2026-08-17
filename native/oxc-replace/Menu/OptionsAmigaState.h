#pragma once
/*
 * AMIGA-PORT: the "Amiga" options tab. Everything the port adds on top of
 * OpenXcom's own options lives here so it never has to be squeezed into the
 * upstream screens.
 */
#include "OptionsBaseState.h"

namespace OpenXcom
{

class Text;
class ComboBox;

class OptionsAmigaState : public OptionsBaseState
{
private:
	Text *_txtAppBar, *_txtCursor, *_txtFov, *_txtAnim;
	ComboBox *_cbxAppBar, *_cbxCursor, *_cbxFov, *_cbxAnim;
public:
	OptionsAmigaState(OptionsOrigin origin);
	~OptionsAmigaState();
	void cbxAppBarChange(Action *action);
	void cbxCursorChange(Action *action);
	void cbxFovChange(Action *action);
	void cbxAnimChange(Action *action);
};

}
