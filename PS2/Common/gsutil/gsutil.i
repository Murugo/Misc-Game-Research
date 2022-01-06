%module gsutil

%include <std_string.i>

%include "stdint.i"
%include "std_vector.i"
namespace std {
   %template(Uint8Vector) vector<uint8_t>;
};
%naturalvar std::Uint8Vector;

%include "gsreg.h"
%include "gsutil.h"

%{
    #include "gsreg.h"
    #include "gsutil.h"
%}

%feature("python:slot", "tp_str", functype="reprfunc") GSRegBITBLTBUF::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegTRXPOS::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegTRXREG::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegTRXDIR::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegTEX0::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegTEX1::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegTEX2::DebugString();
%feature("python:slot", "tp_str", functype="reprfunc") GSRegCLAMP::DebugString();

