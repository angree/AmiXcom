#pragma once
/*
 * AMIGA-PORT: the "Amiga" options tab. Everything the port adds on top of
 * OpenXcom's own options lives here so it never has to be squeezed into the
 * upstream screens. A scrolling TextList like the ADVANCED tab: a row per
 * option, click cycles the value, the description shows in the tooltip
 * area at the bottom - so new options never collide with the layout.
 */
#include "OptionsBaseState.h"

namespace OpenXcom
{

class TextList;

class OptionsAmigaState : public OptionsBaseState
{
private:
	TextList *_lstOptions;
	void updateRow(size_t row);
public:
	OptionsAmigaState(OptionsOrigin origin);
	~OptionsAmigaState();
	void lstOptionsClick(Action *action);
	void lstOptionsMouseOver(Action *action);
	void lstOptionsMouseOut(Action *action);
};

}
