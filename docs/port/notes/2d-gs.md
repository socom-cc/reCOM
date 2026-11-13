# How soCOM builds 2D/textured GS primitives (from the asm; 2026-11-06)

## Frame and DMA shape
- Draw packets are built in scratchpad (0x70000000, two 0x1f30-byte halves: `zSysSprGetPacket` 0x2f5ab0)
  and copied by `zSysFifoKick` 0x2f5900 (fromSPR, ch 8) into a 256 KB MFIFO ring drained by **VIF1**
  (`zSysFifoEnable(1)` 0x2f5b50, CHCR 0x145 chain+TTE). `zSysFifoEnd` 0x2f5a20 = DMA END + VIF FLUSH x2.
- Packets are DMA source chains: `CNT n` tags carrying `VIF NOP; VIF DIRECT n` in the tag's upper half,
  and `REF n -> addr` tags (VIF FLUSH; DIRECT n) to pull static GIF data (texture selects) in place.
  So 2D/state data reaches the GIF on **PATH2** (VIF1 DIRECT).
- Texture/CLUT uploads go separately on **PATH3**: `sceDmaSend(zSys.DmaToGif, chain)` + `sceDmaSync`
  (GIF channel 2, chain mode), synchronously, inside `CGSTexBuffer::Load` 0x2fb610.
- Per frame (`CMenuState::Tick` 0x379240): backplane `RenderUiNode` 0x241cb0, CGSTexBuffer[0]->Load,
  `RenderWorld` 0x244780, foreplane `DrawForeplane` 0x383500, Load again, `zSysFifoEnd`, `zVid_Swap`.
  The frame set-up (FRAME/clear) is `framecode`, kicked by `zvid_KickPacket` as a REF in the MFIFO.

## 2D sprite (`C2DBitmap::MakePacket` 0x3031c0)
```
[REF selQwc -> tex select block ; VIF FLUSH, DIRECT selQwc]   only if textured (= tex->m_dmaRef)
CNT 7 ; VIF NOP, DIRECT 7
GIFtag NLOOP 2 EOP PRE PACKED NREG 3 REGS ST,RGBAQ,XYZ2 (0x412);
       PRIM = SPRITE(6) | TME 0x10 (m_hasTexture) | ABE 0x40 (m_isTrans) | AA1 0x80 (m_isAA); FST=0 (STQ)
ST    = m_NewUV[i] floats (S, T, Q): defaults (0.01,-0.01,0) (0.99,-0.99,1) - T negated, images bottom-up
RGBAQ = vftoi0(m_RGB[i])  (128 = 1.0 modulate, alpha 128 opaque)
XYZ2  = vftoi4(x*m_fXPixel + cam.m_screen.left, y*m_fYPixel + cam.m_screen.top, z, 1/16)
```
- `C2D::Init` 0x303c60: m_fXPixel = m_fYPixel = 1.0; m_p2dcamera m_screen = left 1728 top 1824 (GS
  window offset 2048-320, 2048-224), so screen pixels map 1:1 to the 640x448 frame.
- The node matrix (CStack top) transforms both corners first: p' = x*row0 + y*row1 + z*row2 + row3.
  Foreplane nodes sit at z = 16777210, backplane at 0 (ZTEST decides).
- Vertex packets reach the relocator: `reloc->PreGetSprPacket(handle)` before, `TakeDrawPacket(pkt,qwc)`
  (= zSysFifoKick) after. `C2DVisual::Render` 0x386ec0 calls the object's virtual Draw with the node
  matrix and scales alpha by the opacity stack (thePipe +0x648/+0x650).

## Texture record (`CTexture::Read` 0x2f90e0, "texdat" loaded in place)
- `texdat`: TEXTURE_PARAMS (16 bytes: w, h, size, gsaddr, texelBits/selectQwc/pal_offset/flags),
  u32 skip0, u32 skip1, image at +0x18+skip0, then GIF select block at +size+skip1 (preceded by one
  header qword). Formats: 4->PSMT4 0x14, 8->PSMT8 0x13, 24->PSMCT24, 32->PSMCT32, 16->PSMCT16 (or T8).
- `CVisual::GetTextureSelectBlock_ver2` 0x30d9b0: m_dmaRef = REF qwc->block | FLUSH | DIRECT qwc;
  m_dmaRefVu = REF qwc+2 -> header | STCYCL 1,1 | UNPACK V4-32 (VU path, 3D); MSCALF 0 after the block.
- Select block seen in the data: GIFtag NLOOP 5 A+D: ALPHA_1=0x44, TEX1_1=0x60, TEX0_1, TEXA (TA1 0x80),
  CLAMP_1=0 (repeat). TEX0 e.g. SplashLogo 512x256 T8: TBW 8, PSM 0x13, TW 9, TH 8, TCC 1,
  CPSM CT32, CLD 1. `SetGifPtrs` 0x2f8aa0 finds the TEX0/MIPTBP1/MIPTBP2 data words (ctx 1 or 2).
- GS size in 64-word blocks: `Compute64WordMemoryUsage` 0x2f8c30 (T8 /4, T4 /16, CT16 /2, rounded).
- Palettes (`CTexPalette::Read` 0x2f98b0): "par" PALETTE_PARAMS (gsaddr=id, size, format), "buf" CLUT
  copied to a 128-aligned buffer; uploaded as a 16x16 image of its own format. A texture's palette is
  matched by m_palID (= TEX0.CBP in the file) and asset-lib name in `CGSTexBuffer::Hookup` 0x2fbc50.

## GS memory buffers (`CGSTexBuffer`, `CTexManager::doAddBuffer` 0x2fb190)
- Texture area [CTexture::m_baseAddress, m_endAddress) (zVid texture base/end) split into buffers by
  fraction; the UI relocator uses two halves (0-0.5, 0.5-1). Inside a buffer, palettes then textures
  are laid out contiguously from m_startAddress in 64-word blocks (`MakeChain` 0x2fb9a0,
  `UpdateTextureSelects` 0x2f9f20, which patches TEX0.TBP0 and TEX0.CBP in each select block through
  the cached and the 0x20000000 uncached alias, so no flush is needed).
- Upload chain per image (`refLoadImage` 0x2fb840): `CNT 6` GIFtag A+D x4 BITBLTBUF (DBP, DBW=w/64 min 1,
  DPSM=SPSM=psm) TRXPOS 0 TRXREG w,h TRXDIR 0; GIFtag IMAGE EOP NLOOP=size/16; `REF size/16 -> pixels`
  (split past 0x7fff qwc). Chain ends `END 2`: GIFtag A+D TEXFLUSH. FlushCache(0) before sending.
- `CDblBufTextureRelocator::PreGetSprPacket` 0x380600 (menus): add the handle (+palette) to the half
  being filled, Load(true) (upload now), clear it, flip halves - so each 2D draw uploads its texture
  just before its packet, and the previous draw's texture stays resident while the MFIFO drains.
  `CBatchRelocator` (g_relocBatch, temporary in C2DBitmap::Draw(camera)) does not upload.

## For the 3D stage
- Same select blocks/m_dmaRef feed the 3D path; m_dmaRefVu (UNPACK to VU1) is its VU variant.
- MIPUpdateTextureSelects 0x2f9d00 (mip TBP1-3 patching) is still a stub; Hookup records mip parents.
- Verified on screen: 12 ui2d textures (T8+CLUT and CT32, alpha) drawn as sprites by a temporary test
  (`ui2d-texture-test.png`); the real intro design has no static objects (see report).
