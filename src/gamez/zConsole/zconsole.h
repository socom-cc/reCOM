#ifndef ZCONSOLE_H
#define ZCONSOLE_H

/* port: forward declarations for names this header uses */
class CConsole;
/* @socom-skeleton decl forward */
class CPacket;
/* @socom-skeleton end forward */
/* @socom-skeleton decl 8CAckList */
class CAckList
{
public:
	~CAckList();
	void FindPacket(CPacket *);
};
/* @socom-skeleton end 8CAckList */
/* @socom-skeleton decl 8CHandler */
class CHandler
{
public:
	CHandler(const char *, unsigned int, void (*)(CPacket *, CConsole *, void *), void *);
	~CHandler();
	void Dispatch(CPacket *, CConsole *);
};
/* @socom-skeleton end 8CHandler */
/* @socom-skeleton decl 7CPacket */
class CPacket
{
public:
	virtual ~CPacket();
	virtual void GetPacketMsg();
	static void OnRecvPacket(const void *);
	CPacket(CPacket *, unsigned int, unsigned int);
	CPacket(unsigned int, const void *, unsigned int, unsigned int);
	void CopyTo(void *, int);
	void GetPacketType() const;
	void GetFlags() const;
	void GetPacketID() const;
	void Compare(CPacket *, CPacket *);
};
/* @socom-skeleton end 7CPacket */
/* @socom-skeleton decl 10CPacketMsg */
class CPacketMsg : public CPacket
{
public:
	virtual ~CPacketMsg();
	virtual void GetPacketMsg();
	void GetArgCount() const;
	void GetArg(unsigned int) const;
};
/* @socom-skeleton end 10CPacketMsg */
#endif
