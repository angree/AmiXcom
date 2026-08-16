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
	Text *_txtAppBar, *_txtCursor;
	ComboBox *_cbxAppBar, *_cbxCursor;
public:
	OptionsAmigaState(OptionsOrigin origin);
	~OptionsAmigaState();
	void cbxAppBarChange(Action *action);
	void cbxCursorChange(Action *action);
};

}
