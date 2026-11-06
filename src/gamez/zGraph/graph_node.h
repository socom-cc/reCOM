#ifndef GRAPH_NODE_H
#define GRAPH_NODE_H

/* port: forward declarations for names this header uses */
class CGEdge;
class CGNode
{
public:
	CGNode(const char* name);
	~CGNode();

	CGEdge* FindEdge(CGNode* node);

	void SetName(const char* name);
};

class CGNodeEx : CGNode {};
#endif