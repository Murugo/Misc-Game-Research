#include <string>
#include <vector>

// Helper class for transmitting data to and from simulated GS memory.
class GSHelper {
public:
    GSHelper();
    ~GSHelper() = default;

    void UploadPSMCT32(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, const std::vector<uint8_t>& inbuf);
    void UploadPSMT8(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, const std::vector<uint8_t>& inbuf);
    void UploadPSMT4(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, const std::vector<uint8_t>& inbuf);

    std::vector<uint8_t> DownloadPSMCT32(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh);
    std::vector<uint8_t> DownloadPSMT8(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh);
    std::vector<uint8_t> DownloadPSMT4(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh);

    std::vector<uint8_t> DownloadImagePSMT8(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, int cbp, int cbw, char alpha_reg);
    std::vector<uint8_t> DownloadImagePSMT4(int dbp, int dbw, int dsax, int dsay, int rrw, int rrh, int cbp, int cbw, int csa, char alpha_reg);

    void Clear();

private:
    std::vector<char> mem_;
};
