#ifndef ZMPEG_H
#define ZMPEG_H

class CMPEG
{
public:
	void Uninit();
	/* @socom-skeleton decl 5CMPEG */
public:
	static void Init(void *, int);
	static void Run(const char *, bool, bool);
	static void Tick(int);
	static void IdleTick();
	static void End();
	static unsigned char Done();
	void Loop();
	static void SetMaxHeight(int);
	static void SetDisplayHeight(int);
	/* @socom-skeleton end 5CMPEG */
};
#endif