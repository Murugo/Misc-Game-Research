#include "gsutil.h"

#include <cstring>

namespace {

constexpr int kBlockTablePSMCT32[] = {
    0,  1,  4,  5,  16, 17, 20, 21,
    2,  3,  6,  7,  18, 19, 22, 23,
    8,  9,  12, 13, 24, 25, 28, 29,
    10, 11, 14, 15, 26, 27, 30, 31,
};

constexpr int kColumnTablePSMCT32[] = {
    0,  1,  4,  5,  8,  9,  12, 13,
    2,  3,  6,  7,  10, 11, 14, 15,
};

constexpr int kBlockTablePSMT8[] = {
    0,  1,  4,  5,  16, 17, 20, 21,
    2,  3,  6,  7,  18, 19, 22, 23,
    8,  9,  12, 13, 24, 25, 28, 29,
    10, 11, 14, 15, 26, 27, 30, 31,
};

constexpr int kColumnTablePSMT8[] = {
    0,   4,   16,  20,  32,  36,  48,  52,	 // Column 0
    2,   6,   18,  22,  34,  38,  50,  54,
    8,   12,  24,  28,  40,  44,  56,  60,
    10,  14,  26,  30,  42,  46,  58,  62,
    33,  37,  49,  53,  1,   5,   17,  21,
    35,  39,  51,  55,  3,   7,   19,  23,
    41,  45,  57,  61,  9,   13,  25,  29,
    43,  47,  59,  63,  11,  15,  27,  31,
    96,  100, 112, 116, 64,  68,  80,  84,  // Column 1
    98,  102, 114, 118, 66,  70,  82,  86,
    104, 108, 120, 124, 72,  76,  88,  92,
    106, 110, 122, 126, 74,  78,  90,  94,
    65,  69,  81,  85,  97,  101, 113, 117,
    67,  71,  83,  87,  99,  103, 115, 119,
    73,  77,  89,  93,  105, 109, 121, 125,
    75,  79,  91,  95,  107, 111, 123, 127,
    128, 132, 144, 148, 160, 164, 176, 180,	 // Column 2
    130, 134, 146, 150, 162, 166, 178, 182,
    136, 140, 152, 156, 168, 172, 184, 188,
    138, 142, 154, 158, 170, 174, 186, 190,
    161, 165, 177, 181, 129, 133, 145, 149,
    163, 167, 179, 183, 131, 135, 147, 151,
    169, 173, 185, 189, 137, 141, 153, 157,
    171, 175, 187, 191, 139, 143, 155, 159,
    224, 228, 240, 244, 192, 196, 208, 212,	 // Column 3
    226, 230, 242, 246, 194, 198, 210, 214,
    232, 236, 248, 252, 200, 204, 216, 220,
    234, 238, 250, 254, 202, 206, 218, 222,
    193, 197, 209, 213, 225, 229, 241, 245,
    195, 199, 211, 215, 227, 231, 243, 247,
    201, 205, 217, 221, 233, 237, 249, 253,
    203, 207, 219, 223, 235, 239, 251, 255,
};

constexpr int kBlockTablePSMT4[] = {
    0,  2,  8,  10,
    1,  3,  9,  11,
    4,  6,  12, 14,
    5,  7,  13, 15,
};

constexpr int kColumnTablePSMT4[] = {
    0,   8,   32,  40,  64,  72,  96,  104,  // Column 0
    2,   10,  34,  42,  66,  74,  98,  106,
    4,   12,  36,  44,  68,  76,  100, 108,
    6,   14,  38,  46,  70,  78,  102, 110,
    16,  24,  48,  56,  80,  88,  112, 120,
    18,  26,  50,  58,  82,  90,  114, 122,
    20,  28,  52,  60,  84,  92,  116, 124,
    22,  30,  54,  62,  86,  94,  118, 126,
    65,  73,  97,  105, 1,   9,   33,  41,
    67,  75,  99,  107, 3,   11,  35,  43,
    69,  77,  101, 109, 5,   13,  37,  45,
    71,  79,  103, 111, 7,   15,  39,  47,
    81,  89,  113, 121, 17,  25,  49,  57,
    83,  91,  115, 123, 19,  27,  51,  59,
    85,  93,  117, 125, 21,  29,  53,  61,
    87,  95,  119, 127, 23,  31,  55,  63,
    192, 200, 224, 232, 128, 136, 160, 168,  // Column 1
    194, 202, 226, 234, 130, 138, 162, 170,
    196, 204, 228, 236, 132, 140, 164, 172,
    198, 206, 230, 238, 134, 142, 166, 174,
    208, 216, 240, 248, 144, 152, 176, 184,
    210, 218, 242, 250, 146, 154, 178, 186,
    212, 220, 244, 252, 148, 156, 180, 188,
    214, 222, 246, 254, 150, 158, 182, 190,
    129, 137, 161, 169, 193, 201, 225, 233,
    131, 139, 163, 171, 195, 203, 227, 235,
    133, 141, 165, 173, 197, 205, 229, 237,
    135, 143, 167, 175, 199, 207, 231, 239,
    145, 153, 177, 185, 209, 217, 241, 249,
    147, 155, 179, 187, 211, 219, 243, 251,
    149, 157, 181, 189, 213, 221, 245, 253,
    151, 159, 183, 191, 215, 223, 247, 255,
    256, 264, 288, 296, 320, 328, 352, 360,  // Column 2
    258, 266, 290, 298, 322, 330, 354, 362,
    260, 268, 292, 300, 324, 332, 356, 364,
    262, 270, 294, 302, 326, 334, 358, 366,
    272, 280, 304, 312, 336, 344, 368, 376,
    274, 282, 306, 314, 338, 346, 370, 378,
    276, 284, 308, 316, 340, 348, 372, 380,
    278, 286, 310, 318, 342, 350, 374, 382,
    321, 329, 353, 361, 257, 265, 289, 297,
    323, 331, 355, 363, 259, 267, 291, 299,
    325, 333, 357, 365, 261, 269, 293, 301,
    327, 335, 359, 367, 263, 271, 295, 303,
    337, 345, 369, 377, 273, 281, 305, 313,
    339, 347, 371, 379, 275, 283, 307, 315,
    341, 349, 373, 381, 277, 285, 309, 317,
    343, 351, 375, 383, 279, 287, 311, 319,
    448, 456, 480, 488, 384, 392, 416, 424,  // Column 3
    450, 458, 482, 490, 386, 394, 418, 426,
    452, 460, 484, 492, 388, 396, 420, 428,
    454, 462, 486, 494, 390, 398, 422, 430,
    464, 472, 496, 504, 400, 408, 432, 440,
    466, 474, 498, 506, 402, 410, 434, 442,
    468, 476, 500, 508, 404, 412, 436, 444,
    470, 478, 502, 510, 406, 414, 438, 446,
    385, 393, 417, 425, 449, 457, 481, 489,
    387, 395, 419, 427, 451, 459, 483, 491,
    389, 397, 421, 429, 453, 461, 485, 493,
    391, 399, 423, 431, 455, 463, 487, 495,
    401, 409, 433, 441, 465, 473, 497, 505,
    403, 411, 435, 443, 467, 475, 499, 507,
    405, 413, 437, 445, 469, 477, 501, 509,
    407, 415, 439, 447, 471, 479, 503, 511,
};

int GetBlockIdPSMCT32(int block, int x, int y) {
    const int block_y = (y >> 3) & 0x03;
    const int block_x = (x >> 3) & 0x07;
    return block + ((x >> 1) & ~0x1F) + kBlockTablePSMCT32[(block_y << 3) | block_x];
}

int GetPixelAddressPSMCT32(int block, int width, int x, int y) {
    const int page = (block >> 5) + (y >> 5) * width + (x >> 6);
    const int column_base = ((y >> 1) & 0x03) << 4;
    const int column_y = y & 0x01;
    const int column_x = x & 0x07;
    const int column = column_base + kColumnTablePSMCT32[(column_y << 3) | column_x];
    const int addr = ((page << 11) + (GetBlockIdPSMCT32(block & 0x1F, x & 0x3F, y & 0x1F) << 6) + column);
    return (addr << 2) & 0x003FFFFC;
}

int GetBlockIdPSMT8(int block, int x, int y) {
    const int block_y = (y >> 4) & 0x03;
    const int block_x = (x >> 4) & 0x07;
    return block + ((x >> 2) & ~0x1F) + kBlockTablePSMT8[(block_y << 3) | block_x];

}

int GetPixelAddressPSMT8(int block, int width, int x, int y) {
    const int page = (block >> 5) + (y >> 6) * (width >> 1) + (x >> 7);
    const int column_y = y & 0x0F;
    const int column_x = x & 0x0F;
    const int column = kColumnTablePSMT8[(column_y << 4) | column_x];
    const int addr = (page << 13) + (GetBlockIdPSMT8(block & 0x1F, x & 0x7F, y & 0x3F) << 8) + column;
    return addr;
}

int GetBlockIdPSMT4(int block, int x, int y) {
    const int block_base = ((y >> 6) & 0x01) << 4;
    const int block_y = (y >> 4) & 0x03;
    const int block_x = (x >> 5) & 0x03;
    return block + ((x >> 2) & ~0x1F) + block_base + kBlockTablePSMT4[(block_y << 2) | block_x];
}

int GetPixelAddressPSMT4(int block, int width, int x, int y) {
    const int page = ((block >> 5) + (y >> 7) * (width >> 1) + (x >> 7));
    const int column_y = y & 0x0F;
    const int column_x = x & 0x1F;
    const int column = kColumnTablePSMT4[(column_y << 5) | column_x];
    const int addr = (page << 14) + (GetBlockIdPSMT4(block & 0x1F, x & 0x7F, y & 0x7F) << 9) + column;
    return addr;
}

}  // namespace

GSHelper::GSHelper() {
    mem_.resize(4 * 1024 * 1024);  // 4 MB
}

void GSHelper::UploadPSMCT32(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, const std::vector<uint8_t>& inbuf) {
    int src_addr = 0;
    for (int y = dsay; y < dsay + rrh; ++y) {
        for (int x = dsax; x < dsax + rrw; ++x) {
            const int addr = GetPixelAddressPSMCT32(dbp, dbw, x, y);
            mem_[addr + 0x00] = inbuf[src_addr + 0x00];
            mem_[addr + 0x01] = inbuf[src_addr + 0x01];
            mem_[addr + 0x02] = inbuf[src_addr + 0x02];
            mem_[addr + 0x03] = inbuf[src_addr + 0x03];
            src_addr += 0x04;
        }
    }
}

void GSHelper::UploadPSMT8(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, const std::vector<uint8_t>& inbuf) {
    int src_addr = 0;
    for (int y = dsay; y < dsay + rrh; ++y) {
        for (int x = dsax; x < dsax + rrw; ++x) {
            const int addr = GetPixelAddressPSMT8(dbp, dbw, x, y);
            mem_[addr] = inbuf[src_addr++];
        }
    }
}

void GSHelper::UploadPSMT4(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, const std::vector<uint8_t>& inbuf) {
    int src_addr = 0;
    for (int y = dsay; y < dsay + rrh; ++y) {
        for (int x = dsax; x < dsax + rrw; ++x) {
            const int addr = GetPixelAddressPSMT4(dbp, dbw, x, y);
            const int src_nibble = (inbuf[src_addr >> 1] >> ((src_addr & 0x01) << 2)) & 0x0F;
            mem_[addr >> 1] = (src_nibble << ((addr & 0x01) << 2)) | (mem_[addr >> 1] & (0xF0 >> ((addr & 0x01) << 2)));
            src_addr++;
        }
    }
}

std::vector<uint8_t> GSHelper::DownloadPSMCT32(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh) {
    std::vector<uint8_t> outbuf(rrw * rrh * 4);
    int dst_addr = 0;
    for (int y = dsay; y < dsay + rrh; ++y) {
        for (int x = dsax; x < dsax + rrw; ++x) {
            const int addr = GetPixelAddressPSMCT32(dbp, dbw, x, y);
            outbuf[dst_addr + 0x00] = mem_[addr + 0x00];
            outbuf[dst_addr + 0x01] = mem_[addr + 0x01];
            outbuf[dst_addr + 0x02] = mem_[addr + 0x02];
            outbuf[dst_addr + 0x03] = mem_[addr + 0x03];
            dst_addr += 0x04;
        }
    }
    return outbuf;
}

std::vector<uint8_t> GSHelper::DownloadPSMT8(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh) {
    // Not implemented
    return std::vector<uint8_t>();
}

std::vector<uint8_t> GSHelper::DownloadPSMT4(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh) {
    // Not implemented
    return std::vector<uint8_t>();
}

std::vector<uint8_t> GSHelper::DownloadImagePSMT8(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, int cbp, int cbw, char alpha_reg) {
    std::vector<uint8_t> outbuf(rrw * rrh * 4);
    int dst_addr = 0;
    for (int y = dsay; y < dsay + rrh; ++y) {
        for (int x = dsax; x < dsax + rrw; ++x) {
            const int addr = GetPixelAddressPSMT8(dbp, dbw, x, y);
            const int clut_index = mem_[addr];

            int cy = (clut_index & 0xE0) >> 4;
            int cx = clut_index & 0x07;
            if (clut_index & 0x08) cy++;
            if (clut_index & 0x10) cx += 8;

            const int p = GetPixelAddressPSMCT32(cbp, cbw, cx, cy);
            outbuf[dst_addr + 0x00] = mem_[p + 0x00];
            outbuf[dst_addr + 0x01] = mem_[p + 0x01];
            outbuf[dst_addr + 0x02] = mem_[p + 0x02];
            if (alpha_reg >= 0) {
                outbuf[dst_addr + 0x03] = alpha_reg;
            } else {
                const char src_alpha = mem_[p + 0x03];
                outbuf[dst_addr + 0x03] = src_alpha >= 0 ? (src_alpha << 1) : 0xFF;
            }
            dst_addr += 4;
        }
    }
    return outbuf;
}

std::vector<uint8_t> GSHelper::DownloadImagePSMT4(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, int cbp, int cbw, int csa, char alpha_reg) {
    std::vector<uint8_t> outbuf(rrw * rrh * 4);
    int dst_addr = 0;
    for (int y = dsay; y < dsay + rrh; ++y) {
        for (int x = dsax; x < dsax + rrw; ++x) {
            const int addr = GetPixelAddressPSMT4(dbp, dbw, x, y);
            const int clut_index = (mem_[addr >> 1] >> ((addr & 0x01) << 2)) & 0x0F;

            const int cy = ((clut_index >> 3) & 0x01) + (csa & 0x0E);
            const int cx = (clut_index & 0x07) + ((csa & 0x01) << 3);

            const int p = GetPixelAddressPSMCT32(cbp, cbw, cx, cy);
            outbuf[dst_addr + 0x00] = mem_[p + 0x00];
            outbuf[dst_addr + 0x01] = mem_[p + 0x01];
            outbuf[dst_addr + 0x02] = mem_[p + 0x02];
            if (alpha_reg >= 0) {
                outbuf[dst_addr + 0x03] = alpha_reg;
            } else {
                const char src_alpha = mem_[p + 0x03];
                outbuf[dst_addr + 0x03] = src_alpha >= 0 ? (src_alpha << 1) : 0xFF;
            }
            dst_addr += 4;
        }
    }
    return outbuf;
}

void GSHelper::Clear() {
    memset(mem_.data(), 0, mem_.size() * sizeof(char));
}
