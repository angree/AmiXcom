/*
 * Amiga port replacement for src/Engine/CrossPlatform.cpp.
 *
 * Upstream's version is three platforms in one file - Win32 shell APIs, X11
 * window flashing, POSIX pwd/execinfo backtraces - none of which exist here,
 * and the #ifdef nest needed to add a fourth would be larger than the file
 * this replaces. The public interface (CrossPlatform.h) is unchanged.
 *
 * AmigaOS specifics that shape it:
 *   - Paths are "Volume:dir/file", not "/dir/file". A trailing slash is not
 *     decoration: "Work:foo/" names foo's PARENT, so it has to be stripped
 *     before stat() or mkdir() ever sees it, while OpenXcom's own code
 *     expects endPath() to keep it. Both rules are honoured here.
 *   - Everything lives beside the executable, under PROGDIR: - there is no
 *     home directory and no system-wide data folder to search.
 *   - There is no backtrace and no core dump; a crash writes what it knows to
 *     the log and puts an Intuition requester on screen, because a game that
 *     vanishes with no window is indistinguishable from one that never
 *     started.
 */
#include "CrossPlatform.h"

#include <algorithm>
#include <sstream>
#include <fstream>

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <ctime>
#include <cwchar>

#include <sys/stat.h>
#include <dirent.h>

#include <SDL.h>

#include "Logger.h"
#include "Exception.h"
#include "Options.h"
#include "Language.h"
#include "amiga_startup.h"

namespace OpenXcom
{
namespace CrossPlatform
{
	std::string errorDlg;
	const char PATH_SEPARATOR = '/';

/**
 * Strips the trailing slash AmigaOS reads as "the parent of".
 */
static std::string sysPath(const std::string &path)
{
	std::string p = path;
	while (p.size() > 1 && p[p.size() - 1] == '/')
	{
		// "Work:" keeps its colon; only a real trailing slash goes.
		p.erase(p.size() - 1);
	}
	return p;
}

void getErrorDialog()
{
	// Always the same one here: intuition.library.
}

void showError(const std::string &error)
{
	Log(LOG_FATAL) << error;
	amigastartup_error(error.c_str());
}

/**
 * Data lives next to the executable. PROGDIR: is resolved by AmigaDOS itself,
 * so the game can be started from anywhere - Workbench, a shell in another
 * directory, or User-Startup - and still find its files.
 */
std::vector<std::string> findDataFolders()
{
	std::vector<std::string> list;
	list.push_back("PROGDIR:data/");
	list.push_back("data/");
	list.push_back("PROGDIR:");
	return list;
}

std::vector<std::string> findUserFolders()
{
	std::vector<std::string> list;
	list.push_back("PROGDIR:user/");
	list.push_back("user/");
	return list;
}

std::string findConfigFolder()
{
	return "PROGDIR:user/";
}

std::string searchDataFile(const std::string &filename)
{
	std::string path = Options::getDataFolder() + filename;
	if (fileExists(path)) return path;

	for (std::vector<std::string>::const_iterator i = Options::getDataList().begin(); i != Options::getDataList().end(); ++i)
	{
		path = *i + filename;
		if (fileExists(path))
		{
			Options::setDataFolder(*i);
			return path;
		}
	}
	return filename;
}

std::string searchDataFolder(const std::string &foldername)
{
	std::string path = Options::getDataFolder() + foldername;
	if (folderExists(path)) return path;

	for (std::vector<std::string>::const_iterator i = Options::getDataList().begin(); i != Options::getDataList().end(); ++i)
	{
		path = *i + foldername;
		if (folderExists(path))
		{
			Options::setDataFolder(*i);
			return path;
		}
	}
	return foldername;
}

bool createFolder(const std::string &path)
{
	return mkdir(sysPath(path).c_str(), 0755) == 0;
}

std::string endPath(const std::string &path)
{
	if (path.empty()) return path;
	char last = path[path.size() - 1];
	// A volume or assign ("Work:", "PROGDIR:") is already a complete prefix.
	if (last == PATH_SEPARATOR || last == ':') return path;
	return path + PATH_SEPARATOR;
}

std::vector<std::string> getFolderContents(const std::string &path, const std::string &ext)
{
	std::vector<std::string> files;
	std::string extl = ext;
	std::transform(extl.begin(), extl.end(), extl.begin(), ::tolower);

	DIR *dp = opendir(sysPath(path).c_str());
	if (dp == 0)
	{
		std::string errorMessage("Failed to open directory: " + path);
		throw Exception(errorMessage);
	}

	struct dirent *dirp;
	while ((dirp = readdir(dp)) != 0)
	{
		std::string file = dirp->d_name;

		if (file == "." || file == "..") continue;
		if (!extl.empty())
		{
			if (file.length() >= extl.length() + 1)
			{
				std::string end = file.substr(file.length() - extl.length() - 1);
				std::transform(end.begin(), end.end(), end.begin(), ::tolower);
				if (end != "." + extl) continue;
			}
			else
			{
				continue;
			}
		}
		files.push_back(file);
	}
	closedir(dp);
	std::sort(files.begin(), files.end());
	return files;
}

bool folderExists(const std::string &path)
{
	struct stat info;
	if (stat(sysPath(path).c_str(), &info) != 0) return false;
	return S_ISDIR(info.st_mode);
}

bool fileExists(const std::string &path)
{
	struct stat info;
	if (stat(sysPath(path).c_str(), &info) != 0) return false;
	return S_ISREG(info.st_mode);
}

bool deleteFile(const std::string &path)
{
	return remove(sysPath(path).c_str()) == 0;
}

std::string baseFilename(const std::string &path)
{
	// Both separators count: ':' ends a volume or assign on AmigaOS.
	size_t sep = path.find_last_of(":/");
	std::string filename = (sep == std::string::npos) ? path : path.substr(sep + 1);
	return filename;
}

std::string sanitizeFilename(const std::string &filename)
{
	std::string newFilename = filename;
	for (std::string::iterator i = newFilename.begin(); i != newFilename.end(); ++i)
	{
		if ((*i) == '<' || (*i) == '>' || (*i) == ':' || (*i) == '"' ||
		    (*i) == '/' || (*i) == '?' || (*i) == '\\' || (*i) == '#' || (*i) == '|')
		{
			*i = '_';
		}
	}
	return newFilename;
}

std::string noExt(const std::string &filename)
{
	size_t dot = filename.find_last_of('.');
	if (dot == std::string::npos) return filename;
	return filename.substr(0, dot);
}

/**
 * AmigaOS keeps its language in Locale preferences rather than in the
 * environment, and reading it would mean locale.library plus a mapping table
 * for a value the player can set in the game's own options anyway.
 */
std::string getLocale()
{
	return "en-US";
}

bool isQuitShortcut(const SDL_Event &ev)
{
	// The window close gadget arrives as SDL_QUIT; this is the keyboard
	// equivalent, and Amiga convention puts it on right-Amiga + Q.
	return (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_q &&
	        (ev.key.keysym.mod & (KMOD_LMETA | KMOD_RMETA | KMOD_CTRL)) != 0);
}

time_t getDateModified(const std::string &path)
{
	struct stat info;
	if (stat(sysPath(path).c_str(), &info) != 0) return 0;
	return info.st_mtime;
}

std::pair<std::wstring, std::wstring> timeToString(time_t time)
{
	wchar_t localDate[25], localTime[25];

	struct tm *timeinfo = localtime(&(time));
	wcsftime(localDate, 25, L"%Y-%m-%d", timeinfo);
	wcsftime(localTime, 25, L"%H:%M", timeinfo);

	return std::make_pair(localDate, localTime);
}

bool naturalCompare(const std::wstring &a, const std::wstring &b)
{
	std::wstring::const_iterator i, j;
	for (i = a.begin(), j = b.begin(); i != a.end() && j != b.end() && tolower(*i) == tolower(*j); i++, j++);
	return (i != a.end() && j != b.end() && tolower(*i) < tolower(*j));
}

/**
 * rename() cannot move a file between AmigaDOS volumes, and the save folder
 * and the temporary file are not guaranteed to share one, so this copies and
 * then deletes rather than trusting the fast path to be available.
 */
bool moveFile(const std::string &src, const std::string &dest)
{
	std::string s = sysPath(src), d = sysPath(dest);

	if (rename(s.c_str(), d.c_str()) == 0) return true;

	std::ifstream in(s.c_str(), std::ios::binary);
	if (!in) return false;
	std::ofstream out(d.c_str(), std::ios::binary | std::ios::trunc);
	if (!out) return false;
	out << in.rdbuf();
	if (!out.good()) return false;
	in.close();
	out.close();
	return remove(s.c_str()) == 0;
}

/**
 * There is no taskbar to flash. Making the screen flash instead would be
 * worse than doing nothing: this is called when the game wants attention
 * while the player is in another program, and on a 68k machine that player is
 * far more likely to be annoyed than helped.
 */
void flashWindow()
{
}

/**
 * The loading screen prints a fake DOS prompt. On an Amiga the honest
 * equivalent is the program's own directory.
 */
std::string getDosPath()
{
	return "PROGDIR:";
}

void setWindowIcon(int winResource, const std::string &unixPath)
{
	// An Amiga program's icon is the .info file beside it.
	(void)winResource;
	(void)unixPath;
}

/**
 * No execinfo, no dbghelp. What can be said is said in the log.
 */
void stackTrace(void *ctx)
{
	(void)ctx;
	Log(LOG_FATAL) << "(no stack trace available on AmigaOS 68k)";
}

std::string now()
{
	const int MAX_LEN = 25;
	char result[MAX_LEN] = { 0 };
	time_t now = time(0);
	struct tm *timeinfo = localtime(&now);
	if (strftime(result, MAX_LEN, "%Y-%m-%d_%H-%M-%S", timeinfo) == 0) return "";
	return result;
}

void crashDump(void *ex, const std::string &err)
{
	std::ostringstream error;
	error << err;
	(void)ex;

	Log(LOG_FATAL) << "OpenXcom has crashed: " << error.str();
	Log(LOG_FATAL) << "More details here: " << Options::getUserFolder() << "openxcom.log";

	std::ostringstream msg;
	msg << "OpenXcom has crashed:\n" << error.str()
	    << "\n\nMore details in openxcom.log";
	amigastartup_error(msg.str().c_str());
}

}
}
