# 哈希集合法  C++语法

> 来源：ima 个人知识库 · 数据结构 · 第二节习题 · 第 5 题
> 导出时间：2026-10-07
> ⚠️ 原笔记末尾疑似缺少闭合大括号，此处按原文保留，未擅自补全。

## 思路

先把链表 A 的所有结点指针塞进 `unordered_set`，再遍历 B，第一个能在集合里查到的结点就是公共结点。

## 代码（C++ 版本）

```cpp
#include <unordered_set>

LNode* findCommonNode3(LinkList A, LinkList B) {
    std::unordered_set<LNode*> st;
    LNode *p = A->next;
    while(p != NULL){
        st.insert(p);
        p = p->next;
    }
    LNode *q = B->next;
    while(q != NULL){
        if(st.count(q))
            return q;
        q = q->next;
    }
    return NULL;
```

## 复杂度

- 时间：O(lenA + lenB)（哈希查找均摊 O(1)）
- 空间：O(lenA)，需要额外存 A 的全部结点指针
