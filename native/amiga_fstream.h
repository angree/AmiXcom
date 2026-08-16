/*
 * File streams that work on this toolchain.
 *
 * bebbo's m68k-amigaos libstdc++ has a fatal bug in its file streams: closing a
 * successfully opened std::ifstream / std::ofstream never returns. Not a crash
 * - an infinite loop, with the CPU pegged and no output. Proven with a
 * ten-line program: fopen/fclose is fine, an ifstream on a MISSING file closes
 * fine (nothing was opened), and an ifstream on a file that exists hangs in
 * close(). Every destructor calls close(), so every scope exit hangs.
 *
 * OpenXcom reads its options, savegames, rulesets, palettes, terrain and
 * language files through std::ifstream, so this is not a corner case - it is
 * the whole game.
 *
 * The fix is to keep the stream INTERFACE (the game and yaml-cpp are written
 * against it) and put stdio underneath, which works. These classes are drop-in
 * replacements for std::ifstream / std::ofstream for everything the game does
 * with them: construction with a path, open/close/is_open, >>, <<, getline,
 * read/write, seekg/tellg, rdbuf() into a stringstream, and use as a base
 * class (CatFile derives from ifstream).
 */
#ifndef AMIGA_FSTREAM_H
#define AMIGA_FSTREAM_H

#include <cstdio>
#include <cstring>
#include <istream>
#include <ostream>
#include <streambuf>
#include <string>

namespace OpenXcom
{

class AmigaFileBuf : public std::streambuf
{
public:
	AmigaFileBuf() : _file(0), _writing(false) { setg(_in, _in, _in); }
	~AmigaFileBuf() { close(); }

	bool is_open() const { return _file != 0; }

	AmigaFileBuf *open(const char *path, std::ios_base::openmode mode)
	{
		if (_file != 0) return 0;

		const char *m = "rb";
		_writing = (mode & std::ios_base::out) != 0;
		if (_writing)
		{
			if (mode & std::ios_base::app) m = "ab";
			else m = "wb";
		}
		_file = fopen(path, m);
		if (_file == 0) return 0;

		setg(_in, _in, _in);
		return this;
	}

	AmigaFileBuf *close()
	{
		if (_file == 0) return 0;
		sync();
		fclose(_file);
		_file = 0;
		setg(_in, _in, _in);
		return this;
	}

protected:
	int_type underflow()
	{
		if (_file == 0) return traits_type::eof();
		if (gptr() < egptr()) return traits_type::to_int_type(*gptr());

		size_t n = fread(_in, 1, sizeof(_in), _file);
		if (n == 0) return traits_type::eof();
		setg(_in, _in, _in + n);
		return traits_type::to_int_type(*gptr());
	}

	int_type overflow(int_type c)
	{
		if (_file == 0) return traits_type::eof();
		if (c == traits_type::eof()) return traits_type::not_eof(c);
		char ch = traits_type::to_char_type(c);
		if (fwrite(&ch, 1, 1, _file) != 1) return traits_type::eof();
		return c;
	}

	std::streamsize xsputn(const char *s, std::streamsize n)
	{
		if (_file == 0) return 0;
		return (std::streamsize)fwrite(s, 1, (size_t)n, _file);
	}

	int sync()
	{
		if (_file == 0) return -1;
		if (_writing) return fflush(_file) == 0 ? 0 : -1;
		return 0;
	}

	pos_type seekoff(off_type off, std::ios_base::seekdir dir, std::ios_base::openmode which)
	{
		(void)which;
		if (_file == 0) return pos_type(off_type(-1));

		int whence = SEEK_SET;
		if (dir == std::ios_base::cur)
		{
			whence = SEEK_CUR;
			// Characters already read into the buffer have not been consumed
			// by the caller, so the real file position is ahead of where the
			// stream thinks it is.
			off -= (off_type)(egptr() - gptr());
		}
		else if (dir == std::ios_base::end)
		{
			whence = SEEK_END;
		}

		if (fseek(_file, (long)off, whence) != 0) return pos_type(off_type(-1));
		setg(_in, _in, _in);
		return pos_type(ftell(_file));
	}

	pos_type seekpos(pos_type pos, std::ios_base::openmode which)
	{
		return seekoff(off_type(pos), std::ios_base::beg, which);
	}

private:
	FILE *_file;
	bool  _writing;
	char  _in[1024];
};

/// Input file stream, stdio-backed. Interface-compatible with std::ifstream.
class AmigaIFStream : public std::istream
{
public:
	AmigaIFStream() : std::istream(&_buf) {}
	explicit AmigaIFStream(const char *path, std::ios_base::openmode mode = std::ios_base::in)
		: std::istream(&_buf) { open(path, mode); }
	explicit AmigaIFStream(const std::string &path, std::ios_base::openmode mode = std::ios_base::in)
		: std::istream(&_buf) { open(path.c_str(), mode); }

	void open(const char *path, std::ios_base::openmode mode = std::ios_base::in)
	{
		if (_buf.open(path, mode | std::ios_base::in) == 0) setstate(std::ios_base::failbit);
		else clear();
	}
	void open(const std::string &path, std::ios_base::openmode mode = std::ios_base::in) { open(path.c_str(), mode); }

	bool is_open() const { return _buf.is_open(); }
	void close() { if (_buf.close() == 0) setstate(std::ios_base::failbit); }

	AmigaFileBuf *rdbuf() const { return const_cast<AmigaFileBuf *>(&_buf); }

private:
	AmigaFileBuf _buf;
};

/// Output file stream, stdio-backed. Interface-compatible with std::ofstream.
class AmigaOFStream : public std::ostream
{
public:
	AmigaOFStream() : std::ostream(&_buf) {}
	explicit AmigaOFStream(const char *path, std::ios_base::openmode mode = std::ios_base::out)
		: std::ostream(&_buf) { open(path, mode); }
	explicit AmigaOFStream(const std::string &path, std::ios_base::openmode mode = std::ios_base::out)
		: std::ostream(&_buf) { open(path.c_str(), mode); }

	void open(const char *path, std::ios_base::openmode mode = std::ios_base::out)
	{
		if (_buf.open(path, mode | std::ios_base::out) == 0) setstate(std::ios_base::failbit);
		else clear();
	}
	void open(const std::string &path, std::ios_base::openmode mode = std::ios_base::out) { open(path.c_str(), mode); }

	bool is_open() const { return _buf.is_open(); }
	void close() { flush(); if (_buf.close() == 0) setstate(std::ios_base::failbit); }

	AmigaFileBuf *rdbuf() const { return const_cast<AmigaFileBuf *>(&_buf); }

private:
	AmigaFileBuf _buf;
};

}

#endif /* AMIGA_FSTREAM_H */
