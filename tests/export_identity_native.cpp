// Compile with the canonical exporter and installed Sierra headers on include path.
#include "sierra_mcp_bridge.cpp"
#include <stdexcept>
#include <iostream>

void Check(bool condition, const char* message)
{
    if (!condition) throw std::runtime_error(message);
}

int main(int argc, char** argv)
{
    try
    {
        Check(argc == 2, "Supply an isolated test directory");
        const std::string directory = argv[1];
        unsigned char first[4096] = {}, second[4096] = {}, saved[4096] = {};
        Check(EnsureExportIdentity(first, false), "Generate identity");
        Check(EnsureExportIdentity(second, false), "Generate second identity");
        Check(std::memcmp(first, second, sizeof(ExportIdentity)) != 0, "Independent study identities");
        std::memcpy(saved, first, sizeof(saved));
        Check(EnsureExportIdentity(saved, false), "Reload saved identity");
        Check(std::memcmp(first, saved, sizeof(saved)) == 0, "Reopen/rename preserve stored bytes");
        const std::string id = reinterpret_cast<ExportIdentity*>(first)->id;
        const std::string otherID = reinterpret_cast<ExportIdentity*>(second)->id;
        const std::string path = directory + "\\snapshot.json";
        {
            ExportWriter owner, duplicate, samePath, independent;
            Check(owner.Claim(directory, id, path), "First writer claim");
            Check(!duplicate.Claim(directory, id, directory + "\\copy.json"), "Copied identity blocked");
            Check(!samePath.Claim(directory, otherID, path), "Explicit path collision blocked");
            // Failed claim releases its identity handle when destroyed.
        }
        {
            ExportWriter reopened, independent;
            Check(reopened.Claim(directory, id, path), "Claim after close with lock files retained");
            Check(independent.Claim(directory, otherID, directory + "\\second.json"), "Two simultaneous writers");
            std::ofstream(path) << "old";
            const std::string temporary = path + "." + id + ".tmp";
            std::ofstream(temporary) << "new";
            HANDLE reader = CreateFileA(path.c_str(), GENERIC_READ, FILE_SHARE_READ,
                nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            Check(reader != INVALID_HANDLE_VALUE, "Open real Windows reader lock");
            Check(!MoveFileExA(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING), "Reader denies replacement");
            CloseHandle(reader);
            std::string content;
            { std::ifstream input(path); input >> content; }
            Check(content == "old", "Failed replacement preserves previous snapshot");
            Check(MoveFileExA(temporary.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING) != 0, "Replacement recovers after reader closes");
            { std::ifstream input(path); input >> content; }
            Check(content == "new", "Recovered snapshot is complete");
        }
        Check(EnsureExportIdentity(saved, true), "Explicit reset");
        Check(std::memcmp(first, saved, sizeof(ExportIdentity)) != 0, "Reset assigns new identity");
        saved[0] = '!';
        Check(!EnsureExportIdentity(saved, false), "Unknown storage fails closed");
        Check(!EnsureExportIdentity(nullptr, false), "Missing storage fails closed");
        std::cout << "Native identity, collision, reopen, reset and Windows replacement checks passed\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
