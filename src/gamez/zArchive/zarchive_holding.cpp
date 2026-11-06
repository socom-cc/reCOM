/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zArchive/zar.h"

/* @socom-skeleton body __dt__Q23zar4CKeyFv */
/* held from src/gamez/zArchive/zar_main.cpp:21 */
namespace zar {
CKey::~CKey()
	{
		clear();
	}
}

/* @socom-skeleton body Write__Q23zar4CKeyFPQ23zar4CZARP7__sFILE */
/* held from src/gamez/zArchive/zar_main.cpp:102 */
/* port: not in the ELF (only Write__Q23zar4CKeyFPQ23zar4CZAR, zar_search.cpp) */
#if 0
namespace zar {
bool CKey::Write(CZAR* archive, FILE* file)
	{
		archive->Securify(m_name, 4);
		fwrite(m_name, 1, sizeof(s32), file);
		archive->Unsecurify(m_name, 4);

		archive->Securify(&m_offset, 4);
		fwrite(&m_offset, 1, sizeof(s32), file);
		archive->Unsecurify(&m_offset, 4);

		archive->Securify(&m_size, 4);
		fwrite(&m_size, 1, sizeof(s32), file);
		archive->Unsecurify(&m_size, 4);

		archive->Securify(this, 4);
		fwrite(this, 1, sizeof(s32), file);
		archive->Unsecurify(this, 4);

		for (auto i = begin(); i != end(); ++i)
		{
			CKey* key = *i;
			key->Write(archive, file);
		}

		return true;
	}
}
#endif

/* @socom-skeleton body ReadDirectory_V2__Q23zar4CZARFiUi */
/* held from src/gamez/zArchive/zar_main.cpp:676 */
/* port: not in the ELF (only ReadDirectory__Q23zar4CZARFiUi, zar_main.cpp) */
#if 0
namespace zar {
bool CZAR::ReadDirectory_V2(s32 appver, u32 mode)
	{
		CBufferIO bufferIO;
		s32 padding, key_ofs = 0;
		size_t key_size, header_size = 0;

		void* stable_ptr = NULL;
		void* key_ptr = NULL;
		
		// No file memory allocator?
		if (!m_pFileAlloc)
			return false;

		// Is the file open?
		if (!m_pFileAlloc->IsOpen())
			return false;

		// Is the file corrupted/invalid?
		if (m_pFileAlloc->fseek(0, SEEK_SET) == -1)
			return false;

		header_size = m_pFileAlloc->fread(&m_head, sizeof(HEAD));

		if (header_size != sizeof(HEAD))
			return false;

		// Deobfuscate the header.
		Unsecurify(&m_head, sizeof(HEAD));
		
		// Is this ZAR version compatible?
		if (m_head.version != ZAR_VERSION_2)
			return false;

		stable_ptr = zmalloc(m_head.stable_size);

		// Read key names into memory.
		m_pFileAlloc->fread(stable_ptr, m_head.stable_size);

		// Deobfuscate the string table contents.
		Unsecurify(stable_ptr, m_head.stable_size);

		// If a table already exists, destroy it.
		// Populate the new table with our strings.
		m_stable->Destroy();
		m_stable->LoadTable(stable_ptr, m_head.stable_size, true);

		// Clean out the key buffers and prepare them for new keys.
		// A reservation here is made to reduce future allocations.
		m_key_buffer.clear();
		m_key_buffer.reserve(m_head.key_count);

		m_root->erase(m_root->begin(), m_root->end());

		key_size = (s64)m_head.key_count << 4;
		key_ptr = malloc(key_size);

		// Begin reading key bytes into memory.
		// ZAR keys have the option of being "securified",
		// which means their data is scrambled.
		m_pFileAlloc->fread(key_ptr, key_size);
		Unsecurify(key_ptr, key_size);

		bufferIO.Open(key_ptr, key_size);

		// Keys can contain other keys. The root kickstarts the process of
		// adding its children to their keyring.
		// 
		// ZAR headers have a field to keep track of where the string table
		// should be put in memory. (m_tail.stable_ofs)
		// 
		// The field is then subtracted from where the string table is allocated,
		// which is then used as an input here to retrieve what the key's name is in memory.
		m_root->Read(this, &bufferIO, (s64)stable_ptr - m_head.stable_ofs);
		bufferIO.Close();

		// Calculate the alignment per key.
		// This is a new field exclusive to SOCOM 1 and beyond.
		padding = m_head.padding;
		key_ofs = key_size + m_head.stable_size + sizeof(HEAD);
		s32 align = key_ofs % padding;

		padding = !align ? 0 : padding - align;

		m_pFileAlloc->fseek(padding, SEEK_CUR);

		if ((mode & 32) == 0)
		{
			if (header_size != 0)
			{
				m_databuffer_size = m_head.offset;
				m_databuffer = zmalloc(m_databuffer_size);
				m_rootOffset = padding + key_ofs;
				m_pFileAlloc->fseek(m_rootOffset, SEEK_CUR);
				m_pFileAlloc->fread(m_databuffer, m_databuffer_size);
				Unsecurify(m_databuffer, m_databuffer_size);

				if (m_pFileAlloc != NULL)
				{
					m_pFileAlloc->Close();
					delete m_pFileAlloc;

					m_pFile = NULL;
					m_pFileAlloc = NULL;

					m_pFileAlloc = new CFileIO();
					m_pFile = new CBufferIO();

					m_pFile->Open(m_databuffer, m_databuffer_size);
					m_rootOffset = 0;
				}
			}
		}
		else
		{
			m_rootOffset = padding + key_ofs;
		}

		return true;
	}
}
#endif

/* @socom-skeleton body WriteDirectory__Q23zar4CZARFP7__sFILE */
/* held from src/gamez/zArchive/zar_main.cpp:846 */
/* port: not in the ELF (only WriteDirectory__Q23zar4CZARFv, zar_main.cpp) */
#if 0
namespace zar {
bool CZAR::WriteDirectory(FILE* file)
	{
		bool success = false;

		if (!file)
			return false;

		fwrite((void*)m_pFile->m_file, 1, m_pFile->m_filesize, file);

		if (fseek(file, 0, SEEK_END) == -1)
			return false;

		m_tail.version = ZAR_VERSION_1;
		m_tail.offset = ftell(file);
		m_tail.key_count = _countKeys(m_root);
		m_stable->Pack(CKey::fixupKey, m_root);
		m_tail.stable_size = m_stable->m_bytes;
		m_tail.stable_ofs = (s32)m_stable->m_buffer;

		if (!m_bSecure)
		{
			fwrite(m_stable->m_buffer, 1, m_stable->m_bytes, file);
			s32 pos = ftell(file);
			s32 align = pos % 16;
			s32 nextpos = 16 - align;
			char padding = '\0';

			for (u32 i = 0; i < nextpos; i++)
				fwrite(&padding, 1, 1, file);
		}
		else
		{
			void* array = zcalloc(1, m_stable->m_bytes);
			memcpy(array, m_stable->m_buffer, m_stable->m_bytes);
			Securify(array, m_stable->m_bytes);
			m_pFile->fwrite(array, m_stable->m_bytes);
			zfree(array);
		}

		m_root->Write(this, file);
		Securify(&m_tail, sizeof(TAIL));
		fwrite(&m_tail, 1, sizeof(TAIL), file);
		Unsecurify(&m_tail, sizeof(TAIL));

		m_modified = false;

		return success;
	}
}
#endif
