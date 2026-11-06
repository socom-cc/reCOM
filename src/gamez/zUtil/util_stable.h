#ifndef ZUTIL_STABLE_H
#define ZUTIL_STABLE_H
#include <vector>

#include "gamez/zSystem/zsys.h"

namespace zar
{
	class CKey;
}

class CSTable : public std::vector<char*>
{
public:
	CSTable();
	CSTable(size_t size, size_t count);
	~CSTable();

	void LoadTable(void* buffer, size_t bytes, bool owner);

	void ReleaseBuffer(bool owner);
	void Destroy();

	char* CreateString(const char* str);

	/* Pack: the binary has only Pack__7CSTableFPFP7CSTablePv_vPv, declared below */

	int Relocate(char* buffer);

	bool m_owner;
	char* m_buffer;
	u32 m_bytes;
	u32 m_reserve;
	/* @socom-skeleton decl 7CSTable */
public:
	int Relocate(void *);
	unsigned int Pack(void (*)(CSTable *, void *), void *);
	void Clear();
	char * FindString(const char *) const;
	/* @socom-skeleton end 7CSTable */
};
#endif