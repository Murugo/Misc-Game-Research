#include <stdint.h>
#include <string>

enum GSRegister {
    PRIM       = 0x00,
    RGBAQ      = 0x01,
    ST         = 0x02,
    UV         = 0x03,
    XYZF2      = 0x04,
    XYZ2       = 0x05,
    TEX0_1     = 0x06,
    TEX0_2     = 0x07,
    CLAMP_1    = 0x08,
    CLAMP_2    = 0x09,
    FOG        = 0x0A,
    XYZF3      = 0x0C,
    XYZ3       = 0x0D,
    TEX1_1     = 0x14,
    TEX1_2     = 0x15,
    TEX2_1     = 0x16,
    TEX2_2     = 0x17,
    XYOFFSET_1 = 0x18,
    XYOFFSET_2 = 0x19,
    PRMODECONT = 0x1A,
    PRMODE     = 0x1B,
    TEXCLUT    = 0x1C,
    SCANMSK    = 0x22,
    MIPTBP1_1  = 0x34,
    MIPTBP1_2  = 0x35,
    MIPTBP2_1  = 0x36,
    MIPTBP2_2  = 0x37,
    TEXA       = 0x3B,
    FOGCOL     = 0x3D,
    TEXFLUSH   = 0x3F,
    SCISSOR_1  = 0x40,
    SCISSOR_2  = 0x41,
    ALPHA_1    = 0x42,
    ALPHA_2    = 0x43,
    DIMX       = 0x44,
    DTHE       = 0x45,
    COLCLAMP   = 0x46,
    TEST_1     = 0x47,
    TEST_2     = 0x48,
    PABE       = 0x49,
    FBA_1      = 0x4A,
    FBA_2      = 0x4B,
    FRAME_1    = 0x4C,
    FRAME_2    = 0x4D,
    ZBUF_1     = 0x4E,
    ZBUF_2     = 0x4F,
    BITBLTBUF  = 0x50,
    TRXPOS     = 0x51,
    TRXREG     = 0x52,
    TRXDIR     = 0x53,
    HWREG      = 0x54,
    SIGNAL     = 0x60,
    FINISH     = 0x61,
    LABEL      = 0x62
};

enum GSPixelStorageFormat {
    PSMCT32  = 0x00,
    PSMCT24  = 0x01,
    PSMCT16  = 0x02,
    PSMCT16S = 0x0A,
    PSMT8    = 0x13,
    PSMT4    = 0x14,
    PSMT8H   = 0x1B,
    PSMT4HL  = 0x24,
    PSMT4HH  = 0x2C,
    PSMZ32   = 0x30,
    PSMZ24   = 0x31,
    PSMZ16   = 0x32,
    PSMZ16S  = 0x3A
};

enum GSPixelTransmissionOrder {
    UPPER_LEFT_TO_LOWER_RIGHT = 0,
    LOWER_LEFT_TO_UPPER_RIGHT = 1,
    UPPER_RIGHT_TO_LOWER_LEFT = 2,
    LOWER_RIGHT_TO_UPPER_LEFT = 3
};

enum GSTransmissionDirection {
    HOST_TO_LOCAL = 0,
    LOCAL_TO_HOST = 1,
    LOCAL_TO_LOCAL = 2,
    DEACTIVATED = 3
};

enum GSTextureColorComponent {
    RGB = 0,
    RGBA = 1
};

enum GSTextureFunction {
    MODULATE = 0,
    DECAL = 1,
    HIGHLIGHT = 2,
    HIGHLIGHT2 = 3
};

enum GSClutPixelStorageFormat {
    CLUT_PSMCT32 = 0,
    CLUT_PSMCT16 = 2,
    CLUT_PSMCT16S = 10
};

enum GSClutStorageMode {
    CSM1 = 0,
    CSM2 = 1
};

enum GSWrapMode {
    REPEAT = 0,
    CLAMP = 1,
    REGION_CLAMP = 2,
    REGION_REPEAT = 3
};

enum GSTextureFilter {
    NEAREST = 0,
    LINEAR = 1,
    NEAREST_MIPMAP_NEAREST = 2,
    NEAREST_MIPMAP_LINEAR = 3,
    LINEAR_MIPMAP_NEAREST = 4,
    LINEAR_MIPMAP_LINEAR = 5
};

struct GSRegBITBLTBUF {
    uint16_t sbp = 0;
    uint16_t sbw = 0;
    uint8_t spsm = 0;
    uint16_t dbp = 0;
    uint16_t dbw = 0;
    uint8_t dpsm = 0;

    GSRegBITBLTBUF() {}
    GSRegBITBLTBUF(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegTRXPOS {
    uint16_t ssax = 0;
    uint16_t ssay = 0;
    uint16_t dsax = 0;
    uint16_t dsay = 0;
    uint8_t dir = 0;

    GSRegTRXPOS() {}
    GSRegTRXPOS(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegTRXREG {
    uint16_t rrw = 0;
    uint16_t rrh = 0;

    GSRegTRXREG() {}
    GSRegTRXREG(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegTRXDIR {
    uint8_t xdir = 0;

    GSRegTRXDIR() {}
    GSRegTRXDIR(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegTEX0 {
    uint16_t tbp0 = 0;
    uint16_t tbw = 0;
    uint16_t psm = 0;
    uint16_t tw = 0;
    uint16_t th = 0;
    uint16_t tcc = 0;
    uint16_t tfx = 0;
    uint16_t cbp = 0;
    uint16_t cpsm = 0;
    uint16_t csm = 0;
    uint16_t csa = 0;
    uint16_t cld = 0;

    GSRegTEX0() {}
    GSRegTEX0(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegCLAMP {
    uint8_t wms = 0;
    uint8_t wmt = 0;
    uint16_t minu = 0;
    uint16_t maxu = 0;
    uint16_t minv = 0;
    uint16_t maxv = 0;

    GSRegCLAMP() {}
    GSRegCLAMP(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegTEX1 {
    uint8_t lcm = 0;
    uint8_t mxl = 0;
    uint8_t mmag = 0;
    uint8_t mmin = 0;
    uint8_t mtba = 0;
    uint8_t l = 0;
    uint16_t k = 0;

    GSRegTEX1() {}
    GSRegTEX1(uint64_t data);
    uint64_t Data();
    std::string DebugString();
};

struct GSRegTEX2 {
    uint8_t psm = 0;
    uint16_t cbp = 0;
    uint8_t cpsm = 0;
    uint8_t csm = 0;
    uint8_t csa = 0;
    uint8_t cld = 0;

    GSRegTEX2() {}
    GSRegTEX2(uint64_t data);
    GSRegTEX2(const GSRegTEX0& tex0)
        : psm(tex0.psm), cbp(tex0.cbp), cpsm(tex0.cpsm),
          csm(tex0.csm), csa(tex0.csa), cld(tex0.cld) {}
    uint64_t Data();
    std::string DebugString();
};