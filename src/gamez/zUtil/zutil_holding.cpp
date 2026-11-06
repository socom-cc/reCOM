/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <string.h>
#include "gamez/zUtil/zutil.h"
#include "gamez/zUtil/util_stable.h"
#include "gamez/zUtil/util_systemio.h"

/* @socom-skeleton body dumpLog */
/* held from src/gamez/zUtil/util_output.cpp:5 */
bool dumpLog = true; /* port: unproven - not in the ELF; Apps/FTS/main.cpp:110 still reads it */

/* @socom-skeleton body __ct__7CSTableFv */
/* held from src/gamez/zUtil/util_stable.cpp:5 */
CSTable::CSTable() /* port: unproven - not in the ELF (only __ct__7CSTableFUiUi); by-value CSTable members still default-construct */
{
	m_owner = false;
	m_buffer = NULL;
	m_bytes = 0;
	m_reserve = 0;
}

/* @socom-skeleton body fwrite__3CIOFPCc */
/* held from src/gamez/zUtil/util_systemio.cpp:5 */
size_t CIO::fwrite(const char* buf)
{
	size_t size = 0;

	if (buf == NULL)
	{
		size = 0;
	}
	else
	{
		size = strlen(buf);
	}

	size_t bytesWritten = fwrite(&size, 4);

	if (buf != NULL)
	{
		size_t bufBytesWritten = fwrite(buf, size);
		bytesWritten += bufBytesWritten;
	}

	return bytesWritten;
}

/* @socom-skeleton body GetMode__7CFileIOCFv */
/* held from src/gamez/zUtil/util_systemio.cpp:76 */
unsigned int CFileIO::GetMode() const
{
	return m_mode;
}

/* @socom-skeleton body GetSize__7CFileIOCFv */
/* held from src/gamez/zUtil/util_systemio.cpp:81 */
size_t CFileIO::GetSize() const
{
	return m_filesize;
}

/* @socom-skeleton body fwrite__7CFileIOFPCc */
/* held from src/gamez/zUtil/util_systemio.cpp:122 */
size_t CFileIO::fwrite(const char* buf)
{
	size_t length = 0;

	if (buf == NULL)
	{
		return 0;
	}
	else
	{
		length = strlen(buf);
	}

	size_t writeBufResult = fwrite(&length, sizeof(char*));
	size_t writeStrResult = fwrite(buf, length);
	return writeStrResult + writeBufResult;
}
