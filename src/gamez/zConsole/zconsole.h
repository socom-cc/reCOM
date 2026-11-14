#ifndef ZCONSOLE_H
#define ZCONSOLE_H

#include <list>

/* port: forward declarations for names this header uses */
class CConsole;
class CPacketMsg;
/* @socom-skeleton decl forward */
class CPacket;
/* @socom-skeleton end forward */

/* The DECI2 packet a CPacket owns (CPacket::m_data): a 24-byte header, then the payload. No
 * DWARF; layout from the CPacket ctors 0x1ed790 / 0x1ed870, OnRecvPacket 0x1ed930 and the
 * getters. Names invented. */
struct CPacketHeader
{
	unsigned short m_len;   /* +0x0: bytes, header included */
	unsigned short m_rsvd;  /* +0x2: 0 */
	unsigned short m_proto; /* +0x4: DECI2 protocol 0xe000 */
	unsigned char m_src;    /* +0x6: 'E' (swapped with m_dst in an answer) */
	unsigned char m_dst;    /* +0x7: 'H' */
	unsigned int m_id;      /* +0x8: _counter */
	unsigned int m_flags;   /* +0xc: CPacket::FLAG_* */
	unsigned int m_type;    /* +0x10: a CHandler's type (1 ping, 2 msg, 3 error, 4 any) */
	unsigned int m_argc;    /* +0x14: CPacketMsg: strings after the header */
};

/* @socom-skeleton decl 8CAckList */
/* The packets sent with FLAG_WANTACK, waiting for their answer (CConsole +0x8). The ELF's
 * FindPacket / dtor walk `this` as the list itself. */
class CAckList : public std::list<CPacket *>
{
public:
	~CAckList();
	CPacket *FindPacket(CPacket *);
};
/* @socom-skeleton end 8CAckList */
/* @socom-skeleton decl 8CHandler */
/* 16 bytes (__nw 16 in OnConnect 0x1ec8a0); layout from the ctor 0x1ec790. */
class CHandler
{
public:
	CHandler(const char *, unsigned int, void (*)(CPacket *, CConsole *, void *), void *);
	~CHandler();
	bool Dispatch(CPacket *, CConsole *);

	char *m_name;                                   /* +0x0: strdup'd */
	unsigned int m_type;                            /* +0x4 */
	void (*m_func)(CPacket *, CConsole *, void *);  /* +0x8 */
	void *m_data;                                   /* +0xc: the callback's last argument */
};
/* @socom-skeleton end 8CHandler */
/* @socom-skeleton decl 7CPacket */
/* 12 bytes (__nw 12 in RecvPacket 0x1ecf68 / OnRecvPacket 0x1eda78). */
class CPacket
{
public:
	enum { FLAG_WANTACK = 1, FLAG_ACK = 2 }; /* Debug 0x1eca50 prints these names */
	virtual ~CPacket();
	virtual CPacketMsg *GetPacketMsg();
	static CPacket *OnRecvPacket(const void *);
	CPacket(CPacket *, unsigned int, unsigned int);
	CPacket(unsigned int, const void *, unsigned int, unsigned int);
	int CopyTo(void *, int);
	unsigned int GetPacketType() const;
	unsigned int GetFlags() const;
	unsigned int GetPacketID() const;
	static bool Compare(CPacket *, CPacket *);

protected:
	/* port: no symbol - OnRecvPacket 0x1ed930 builds its packets inline (vptr, then both
	 * words cleared) */
	CPacket() : m_data(0), m_size(0) {}
	CPacketHeader *Header() const { return (CPacketHeader *)m_data; }

	friend class CConsole;
	unsigned char *m_data; /* +0x4: calloc'd header + payload */
	unsigned int m_size;   /* +0x8 */
};
/* @socom-skeleton end 7CPacket */
/* @socom-skeleton decl 10CPacketMsg */
/* 16 bytes: a packet whose payload is m_argc NUL-terminated strings. */
class CPacketMsg : public CPacket
{
public:
	virtual ~CPacketMsg();
	virtual CPacketMsg *GetPacketMsg();
	unsigned int GetArgCount() const;
	const char *GetArg(unsigned int) const;

protected:
	/* port: no symbol - built inline by OnRecvPacket 0x1ed930 */
	CPacketMsg() : m_args(0) {}
	friend class CPacket;
	const char **m_args; /* +0xc: calloc'd, one pointer per string into m_data */
};
/* @socom-skeleton end 10CPacketMsg */
#endif
