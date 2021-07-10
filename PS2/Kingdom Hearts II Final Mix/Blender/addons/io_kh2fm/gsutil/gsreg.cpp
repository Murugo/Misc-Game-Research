#include "gsreg.h"

#include <sstream>

#define GET_BITFIELD(val, first, last) (val >> first) & ((1 << (last - first + 1)) - 1)
#define PUT_BITFIELD(val, first, last) ((uint64_t)val & ((1 << (last - first + 1)) - 1)) << first

namespace {

constexpr const char* kUnknown = "Unknown";

const char* PixelStorageFormatStr(GSPixelStorageFormat psm) {
    switch (psm) {
        case GSPixelStorageFormat::PSMCT32: return "PSMCT32";
        case GSPixelStorageFormat::PSMCT24: return "PSMCT24";
        case GSPixelStorageFormat::PSMCT16: return "PSMCT16";
        case GSPixelStorageFormat::PSMCT16S: return "PSMCT16S";
        case GSPixelStorageFormat::PSMT8: return "PSMT8";
        case GSPixelStorageFormat::PSMT4: return "PSMT4";
        case GSPixelStorageFormat::PSMT8H: return "PSMT8H";
        case GSPixelStorageFormat::PSMT4HL: return "PSMT4HL";
        case GSPixelStorageFormat::PSMT4HH: return "PSMT4HH";
        case GSPixelStorageFormat::PSMZ32: return "PSMZ32";
        case GSPixelStorageFormat::PSMZ24: return "PSMZ24";
        case GSPixelStorageFormat::PSMZ16: return "PSMZ16";
        case GSPixelStorageFormat::PSMZ16S: return "PSMZ16S";
        default: return kUnknown;
    }
}

const char* PixelTransmissionOrderStr(GSPixelTransmissionOrder dir) {
    switch (dir) {
        case GSPixelTransmissionOrder::UPPER_LEFT_TO_LOWER_RIGHT: return "UpperLeft->LowerRight";
        case GSPixelTransmissionOrder::LOWER_LEFT_TO_UPPER_RIGHT: return "LowerLeft->UpperRight";
        case GSPixelTransmissionOrder::UPPER_RIGHT_TO_LOWER_LEFT: return "UpperRight->LowerLeft";
        case GSPixelTransmissionOrder::LOWER_RIGHT_TO_UPPER_LEFT: return "LowerRight->UpperLeft";
        default: return kUnknown;
    }
}

const char* TransmissionDirectionStr(GSTransmissionDirection xdir) {
    switch (xdir) {
        case GSTransmissionDirection::HOST_TO_LOCAL: return "Host->Local";
        case GSTransmissionDirection::LOCAL_TO_HOST: return "Local->Host";
        case GSTransmissionDirection::LOCAL_TO_LOCAL: return "Local->Host";
        case GSTransmissionDirection::DEACTIVATED: return "Deactivated";
        default: return kUnknown;
    }
}

const char* TextureColorComponentStr(GSTextureColorComponent tcc) {
    switch (tcc) {
        case GSTextureColorComponent::RGB: return "RGB";
        case GSTextureColorComponent::RGBA: return "RGBA";
        default: return kUnknown;
    }
}

const char* TextureFunctionStr(GSTextureFunction tfx) {
    switch (tfx) {
        case GSTextureFunction::MODULATE: return "MODULATE";
        case GSTextureFunction::DECAL: return "DECAL";
        case GSTextureFunction::HIGHLIGHT: return "HIGHLIGHT";
        case GSTextureFunction::HIGHLIGHT2: return "HIGHLIGHT2";
        default: return kUnknown;
    }
}

const char* ClutPixelStorageFormatStr(GSClutPixelStorageFormat cpsm) {
    switch (cpsm) {
        case GSClutPixelStorageFormat::CLUT_PSMCT32: return "PSMCT32";
        case GSClutPixelStorageFormat::CLUT_PSMCT16: return "PMCT16";
        case GSClutPixelStorageFormat::CLUT_PSMCT16S: return "PSMCT16S";
        default: return kUnknown;
    }
}

const char* ClutStorageModeStr(GSClutStorageMode csm) {
    switch (csm) {
        case GSClutStorageMode::CSM1: return "CSM1";
        case GSClutStorageMode::CSM2: return "CSM2";
        default: return kUnknown;
    }
}

const char* WrapModeStr(GSWrapMode wm) {
    switch (wm) {
        case GSWrapMode::REPEAT: return "REPEAT";
        case GSWrapMode::CLAMP: return "CLAMP";
        case GSWrapMode::REGION_CLAMP: return "REGION_CLAMP";
        case GSWrapMode::REGION_REPEAT: return "REGION_REPEAT";
        default: return kUnknown;
    }
}

const char* TextureFilterStr(GSTextureFilter wm) {
    switch (wm) {
        case GSTextureFilter::NEAREST: return "NEAREST";
        case GSTextureFilter::LINEAR: return "LINEAR";
        case GSTextureFilter::NEAREST_MIPMAP_NEAREST: return "NEAREST_MIPMAP_NEAREST";
        case GSTextureFilter::NEAREST_MIPMAP_LINEAR: return "NEAREST_MIPMAP_LINEAR";
        case GSTextureFilter::LINEAR_MIPMAP_NEAREST: return "LINEAR_MIPMAP_NEAREST";
        case GSTextureFilter::LINEAR_MIPMAP_LINEAR: return "LINEAR_MIPMAP_LINEAR";
        default: return kUnknown;
    }
}

}  // namespace

GSRegBITBLTBUF::GSRegBITBLTBUF(uint64_t data) {
    sbp = GET_BITFIELD(data, 0, 13);
    sbw = GET_BITFIELD(data, 16, 21);
    spsm = GET_BITFIELD(data, 24, 29);
    dbp = GET_BITFIELD(data, 32, 45);
    dbw = GET_BITFIELD(data, 48, 53);
    dpsm = GET_BITFIELD(data, 56, 61);
}

uint64_t GSRegBITBLTBUF::Data() {
    uint64_t data = 0;
    data |= PUT_BITFIELD(sbp, 0, 13);
    data |= PUT_BITFIELD(sbw, 16, 21);
    data |= PUT_BITFIELD(spsm, 24, 29);
    data |= PUT_BITFIELD(dbp, 32, 45);
    data |= PUT_BITFIELD(dbw, 48, 53);
    data |= PUT_BITFIELD(dpsm, 56, 61);
    return data;
}

std::string GSRegBITBLTBUF::DebugString() {
    std::stringstream str;
    str << "{SBP: " << std::hex << sbp;
    str << " SBW: " << std::hex << sbw;
    str << " SPSM: " << PixelStorageFormatStr(static_cast<GSPixelStorageFormat>(spsm));
    str << " DBP: " << std::hex << dbp;
    str << " DBW: " << std::hex << dbw;
    str << " DPSM: " << PixelStorageFormatStr(static_cast<GSPixelStorageFormat>(dpsm)) << "}";
    return str.str();
}

GSRegTRXPOS::GSRegTRXPOS(uint64_t data) {
    ssax = GET_BITFIELD(data, 0, 10);
    ssay = GET_BITFIELD(data, 16, 26);
    dsax = GET_BITFIELD(data, 32, 42);
    dsay = GET_BITFIELD(data, 48, 58);
    dir = GET_BITFIELD(data, 59, 60);
}

uint64_t GSRegTRXPOS::Data() {
    uint64_t data = PUT_BITFIELD(ssax, 0, 10);
    data |= PUT_BITFIELD(ssay, 16, 26);
    data |= PUT_BITFIELD(dsax, 32, 42);
    data |= PUT_BITFIELD(dsay, 48, 58);
    data |= PUT_BITFIELD(dir, 59, 60);
    return data;
}

std::string GSRegTRXPOS::DebugString() {
    std::stringstream str;
    str << "{SSAX: " << std::hex << ssax;
    str << " SSAY: " << std::hex << ssay;
    str << " DSAX: " << std::hex << dsax;
    str << " DSAY: " << std::hex << dsay;
    str << " DIR: " << PixelTransmissionOrderStr(static_cast<GSPixelTransmissionOrder>(dir));
    return str.str();
}

GSRegTRXREG::GSRegTRXREG(uint64_t data) {
    rrw = GET_BITFIELD(data, 0, 11);
    rrh = GET_BITFIELD(data, 32, 43);
}

uint64_t GSRegTRXREG::Data() {
    uint64_t data = PUT_BITFIELD(rrw, 0, 11);
    data |= PUT_BITFIELD(rrh, 32, 43);
    return data;
}

std::string GSRegTRXREG::DebugString() {
    std::stringstream str;
    str << "{RRW: " << std::hex << rrw;
    str << " RRH: " << std::hex << rrh << "}";
    return str.str();
}

GSRegTRXDIR::GSRegTRXDIR(uint64_t data) {
    xdir = GET_BITFIELD(data, 0, 1);
}

uint64_t GSRegTRXDIR::Data() {
    return GET_BITFIELD(xdir, 0, 1);
}

std::string GSRegTRXDIR::DebugString() {
    std::stringstream str;
    str << "{XDIR: " << TransmissionDirectionStr(static_cast<GSTransmissionDirection>(xdir)) << "}";
    return str.str();
}

GSRegTEX0::GSRegTEX0(uint64_t data) {
    tbp0 = GET_BITFIELD(data, 0, 13);
    tbw = GET_BITFIELD(data, 14, 19);
    psm = GET_BITFIELD(data, 20, 25);
    tw = GET_BITFIELD(data, 26, 29);
    th = GET_BITFIELD(data, 30, 33);
    tcc = GET_BITFIELD(data, 34, 34);
    tfx = GET_BITFIELD(data, 35, 36);
    cbp = GET_BITFIELD(data, 37, 50);
    cpsm = GET_BITFIELD(data, 51, 54);
    csm = GET_BITFIELD(data, 55, 55);
    csa = GET_BITFIELD(data, 56, 60);
    cld = GET_BITFIELD(data, 61, 63);
}

uint64_t GSRegTEX0::Data() {
    uint64_t data = PUT_BITFIELD(tbp0, 0, 13);
    data |= PUT_BITFIELD(tbw, 14, 19);
    data |= PUT_BITFIELD(psm, 20, 25);
    data |= PUT_BITFIELD(tw, 26, 29);
    data |= PUT_BITFIELD(th, 30, 33);
    data |= PUT_BITFIELD(tcc, 34, 34);
    data |= PUT_BITFIELD(tfx, 35, 36);
    data |= PUT_BITFIELD(cbp, 37, 50);
    data |= PUT_BITFIELD(cpsm, 51, 54);
    data |= PUT_BITFIELD(csm, 55, 55);
    data |= PUT_BITFIELD(csa, 56, 60);
    data |= PUT_BITFIELD(cld, 61, 63);
    return data;
}

std::string GSRegTEX0::DebugString() {
    std::stringstream str;
    str << "{TBP0: " << std::hex << tbp0;
    str << " TBW: " << std::hex << tbw;
    str << " PSM: " << PixelStorageFormatStr(static_cast<GSPixelStorageFormat>(psm));
    str << " TW: " << std::dec << tw << " (w: " << std::dec << (1 << tw) << ")";
    str << " TH: " << std::dec << th << " (h: " << std::dec << (1 << th) << ")";
    str << " TCC: " << TextureColorComponentStr(static_cast<GSTextureColorComponent>(tcc));
    str << " TFX: " << TextureFunctionStr(static_cast<GSTextureFunction>(tfx));
    str << " CBP: " << std::hex << cbp;
    str << " CPSM: " << ClutPixelStorageFormatStr(static_cast<GSClutPixelStorageFormat>(cpsm));
    str << " CSM: " << ClutStorageModeStr(static_cast<GSClutStorageMode>(csm));
    str << " CSA: " << std::dec << csa;
    str << " CLD: " << std::dec << cld << "}";
    return str.str();
}

GSRegCLAMP::GSRegCLAMP(uint64_t data) {
    wms = GET_BITFIELD(data, 0, 1);
    wmt = GET_BITFIELD(data, 2, 3);
    minu = GET_BITFIELD(data, 4, 13);
    maxu = GET_BITFIELD(data, 14, 23);
    minv = GET_BITFIELD(data, 24, 33);
    maxv = GET_BITFIELD(data, 34, 43);
}

uint64_t GSRegCLAMP::Data() {
    uint64_t data = PUT_BITFIELD(wms, 0, 1);
    data |= PUT_BITFIELD(wmt, 2, 3);
    data |= PUT_BITFIELD(minu, 4, 13);
    data |= PUT_BITFIELD(maxu, 14, 23);
    data |= PUT_BITFIELD(minv, 24, 33);
    data |= PUT_BITFIELD(maxv, 34, 43);
    return data;
}

std::string GSRegCLAMP::DebugString() {
    std::stringstream str;
    str << "{WMS: " << WrapModeStr(static_cast<GSWrapMode>(wms));
    str << " WMT: " << WrapModeStr(static_cast<GSWrapMode>(wmt));
    str << " MINU: " << std::dec << minu;
    str << " MAXU: " << std::dec << maxu;
    str << " MINV: " << std::dec << minv;
    str << " MAXV: " << std::dec << maxv << "}";
    return str.str();
}

GSRegTEX1::GSRegTEX1(uint64_t data) {
    lcm = GET_BITFIELD(data, 0, 0);
    mxl = GET_BITFIELD(data, 2, 4);
    mmag = GET_BITFIELD(data, 5, 5);
    mmin = GET_BITFIELD(data, 6, 8);
    mtba = GET_BITFIELD(data, 9, 9);
    l = GET_BITFIELD(data, 19, 20);
    k = GET_BITFIELD(data, 32, 43);
}

uint64_t GSRegTEX1::Data() {
    uint64_t data = PUT_BITFIELD(lcm, 0, 0);
    data |= PUT_BITFIELD(mxl, 2, 4);
    data |= PUT_BITFIELD(mmag, 5, 5);
    data |= PUT_BITFIELD(mmin, 6, 8);
    data |= PUT_BITFIELD(mtba, 9, 9);
    data |= PUT_BITFIELD(l, 19, 20);
    data |= PUT_BITFIELD(k, 32, 43);
    return data;
}

std::string GSRegTEX1::DebugString() {
    std::stringstream str;
    str << "{LCM: " << std::dec << lcm;
    str << " MXL: " << std::dec << mxl;
    str << " MMAG: " << TextureFilterStr(static_cast<GSTextureFilter>(mmag));
    str << " MMIN: " << TextureFilterStr(static_cast<GSTextureFilter>(mmin));
    str << " MTBA: " << std::dec << mtba;
    str << " L: " << std::dec << l;
    str << " K: " << std::dec << k;
    return str.str();
}

GSRegTEX2::GSRegTEX2(uint64_t data) {
    psm = GET_BITFIELD(data, 20, 25);
    cbp = GET_BITFIELD(data, 37, 50);
    cpsm = GET_BITFIELD(data, 51, 54);
    csm = GET_BITFIELD(data, 55, 55);
    csa = GET_BITFIELD(data, 56, 60);
    cld = GET_BITFIELD(data, 61, 63);
}

uint64_t GSRegTEX2::Data() {
    uint64_t data = PUT_BITFIELD(psm, 20, 25);
    data |= PUT_BITFIELD(cbp, 37, 50);
    data |= PUT_BITFIELD(cpsm, 51, 54);
    data |= PUT_BITFIELD(csm, 55, 55);
    data |= PUT_BITFIELD(csa, 56, 60);
    data |= PUT_BITFIELD(cld, 61, 63);
    return data;
}

std::string GSRegTEX2::DebugString() {
    std::stringstream str;
    str << "{PSM: " << PixelStorageFormatStr(static_cast<GSPixelStorageFormat>(psm));
    str << " CBP: " << std::hex << cbp;
    str << " CPSM: " << ClutPixelStorageFormatStr(static_cast<GSClutPixelStorageFormat>(cpsm));
    str << " CSM: " << ClutStorageModeStr(static_cast<GSClutStorageMode>(csm));
    str << " CSA: " << std::dec << csa;
    str << " CLD: " << std::dec << cld << "}";
    return str.str();
}
