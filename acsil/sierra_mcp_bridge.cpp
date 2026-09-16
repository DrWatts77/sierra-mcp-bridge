#include "sierrachart.h"
#include <fstream>
#include <iomanip>
#include <locale>
#include <sstream>
#include <chrono>
#include <cmath>
#include <cstring>
#include <objbase.h>
#pragma comment(lib, "ole32.lib")

SCDLLName("SierraMCPBridge")

namespace
{
// Only this small, versioned record is saved in Sierra's 4096-byte StorageBlock.
// Runtime handles/pointers must never be persisted in a chartbook.
struct ExportIdentity
{
    char magic[8];
    char id[33];
};

bool EnsureExportIdentity(void* storage, bool reset)
{
    if (!storage) return false;
    ExportIdentity identity = {};
    std::memcpy(&identity, storage, sizeof(identity));
    if (!reset && std::memcmp(identity.magic, "SMBID001", 8) == 0)
    {
        if (identity.id[32] != 0) return false;
        for (int i = 0; i < 32; ++i)
            if (!((identity.id[i] >= '0' && identity.id[i] <= '9')
                || (identity.id[i] >= 'a' && identity.id[i] <= 'f'))) return false;
        return true;
    }
    // Unknown nonzero storage may belong to a future revision. Fail closed.
    if (!reset)
        for (size_t i = 0; i < sizeof(identity); ++i)
            if (static_cast<const unsigned char*>(storage)[i]) return false;
    GUID guid;
    if (FAILED(CoCreateGuid(&guid))) return false;
    std::ostringstream value;
    value << std::hex << std::setfill('0') << std::setw(8) << guid.Data1
        << std::setw(4) << guid.Data2 << std::setw(4) << guid.Data3;
    for (unsigned char byte : guid.Data4) value << std::setw(2) << static_cast<unsigned int>(byte);
    std::memcpy(identity.magic, "SMBID001", 8);
    std::memcpy(identity.id, value.str().c_str(), 33);
    std::memcpy(storage, &identity, sizeof(identity));
    return true;
}

struct ExportWriter
{
    HANDLE identityLock = INVALID_HANDLE_VALUE;
    HANDLE pathLock = INVALID_HANDLE_VALUE;
    std::string path;
    std::string id;
    ~ExportWriter()
    {
        if (pathLock != INVALID_HANDLE_VALUE) CloseHandle(pathLock);
        if (identityLock != INVALID_HANDLE_VALUE) CloseHandle(identityLock);
    }
    bool Claim(const std::string& directory, const std::string& exportID, const std::string& output)
    {
        // Keep lock files: deleting one after closing it would race another claimant.
        identityLock = CreateFileA((directory + "\\" + exportID + ".identity.lock").c_str(),
            GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (identityLock == INVALID_HANDLE_VALUE) return false;
        pathLock = CreateFileA((output + ".writer.lock").c_str(),
            GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (pathLock == INVALID_HANDLE_VALUE) return false;
        path = output;
        id = exportID;
        return true;
    }
};

std::string JsonString(const char* text);
std::string JsonNumber(double value);

std::string ColorHex(uint32_t color)
{
    std::ostringstream out;
    out << "\"#" << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned int>(GetRValue(color))
        << std::setw(2) << static_cast<unsigned int>(GetGValue(color)) << std::setw(2) << static_cast<unsigned int>(GetBValue(color)) << '"';
    return out.str();
}

std::string StudyMetadata(SCStudyInterfaceRef sc, int studyID, int subgraph, int index)
{
    std::ostringstream out;
    out.imbue(std::locale::classic());
    SCString shortName;
    const bool hasShortName = sc.GetChartStudyShortName(sc.ChartNumber, studyID, shortName) != 0;
    uint32_t primary = 0, secondary = 0, secondaryUsed = 0;
    const bool hasColors = sc.GetStudySubgraphColors(sc.ChartNumber, studyID, subgraph, primary, secondary, secondaryUsed) != 0;
    int drawStyle = 0;
    int32_t width = 0;
    SubgraphLineStyles lineStyle;
    const bool hasDraw = sc.GetStudySubgraphDrawStyle(sc.ChartNumber, studyID, subgraph, drawStyle) != 0;
    const bool hasWidth = sc.GetStudySubgraphLineWidth(sc.ChartNumber, studyID, subgraph, width) != 0;
    const bool hasLine = sc.GetStudySubgraphLineStyle(sc.ChartNumber, studyID, subgraph, lineStyle) != 0;
    SCColorArray colors;
    sc.GetStudyDataColorArrayFromChartUsingID(sc.ChartNumber, studyID, subgraph, colors);
    out << "{\"short_name\":" << (hasShortName ? JsonString(shortName.GetChars()) : "null")
        << ",\"primary_color\":" << (hasColors ? ColorHex(primary) : "null")
        << ",\"secondary_color\":" << (hasColors ? ColorHex(secondary) : "null")
        << ",\"secondary_color_used\":" << (hasColors ? (secondaryUsed ? "true" : "false") : "null")
        << ",\"latest_data_color_raw\":" << (colors.GetArraySize() > index ? ColorHex(colors[index]) : "null")
        << ",\"draw_style_code\":" << (hasDraw ? std::to_string(drawStyle) : "null")
        << ",\"line_style_code\":" << (hasLine ? std::to_string(static_cast<int>(lineStyle)) : "null")
        << ",\"line_width\":" << (hasWidth ? std::to_string(width) : "null")
        << ",\"hide_study_setting_raw\":" << sc.GetChartStudyHideStudy(sc.ChartNumber, studyID)
        << ",\"graph_region_raw\":" << sc.GetChartStudyGraphRegion(sc.ChartNumber, studyID)
        << ",\"inputs\":[";
    bool first = true;
    for (int input = 0; input < SC_INPUTS_AVAILABLE; ++input)
    {
        SCString name;
        if (!sc.GetStudyInputName(sc.ChartNumber, studyID, input, name) || name.GetLength() == 0) continue;
        const int type = sc.GetChartStudyInputType(sc.ChartNumber, studyID, input);
        if (type == NO_VALUE) continue;
        std::string value = "null";
        std::string reason = "unsupported_or_text_input";
        int integer = 0;
        double number = 0;
        // Free text and file paths can contain credentials; export their name/type, not content.
        if (type == FLOAT_VALUE || type == DOUBLE_VALUE)
        {
            if (sc.GetChartStudyInputFloat(sc.ChartNumber, studyID, input, number))
            {
                value = JsonNumber(number);
                reason = std::isfinite(number) ? "" : "nonfinite_value";
            }
            else reason = "input_unavailable";
        }
        else if (type == INT_VALUE || type == YESNO_VALUE || type == OHLC_VALUE
            || type == MOVAVGTYPE_VALUE || type == STUDYINDEX_VALUE || type == SUBGRAPHINDEX_VALUE
            || type == STUDYID_VALUE || type == CHART_NUMBER || type == TIME_PERIOD_LENGTH_UNIT_VALUE
            || type == CUSTOM_STRING_VALUE || type == COLOR_VALUE)
        {
            if (sc.GetChartStudyInputInt(sc.ChartNumber, studyID, input, integer))
            {
                value = type == YESNO_VALUE ? (integer ? "true" : "false") : std::to_string(integer);
                reason.clear();
            }
            else reason = "input_unavailable";
        }
        if (!first) out << ',';
        first = false;
        out << "{\"index\":" << input << ",\"name\":" << JsonString(name.GetChars())
            << ",\"type_code\":" << type << ",\"value\":" << value
            << ",\"reason\":" << (reason.empty() ? "null" : JsonString(reason.c_str())) << '}';
    }
    out << "]}";
    return out.str();
}

std::string JsonNumber(double value)
{
    if (!std::isfinite(value)) return "null";
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::setprecision(15) << value;
    return out.str();
}

std::string JsonString(const char* text)
{
    std::ostringstream out;
    out << '"';
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(text); *p; ++p)
    {
        if (*p == '"' || *p == '\\')
            out << '\\' << static_cast<char>(*p);
        else if (*p < 0x20)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(*p);
        else
            out << static_cast<char>(*p);
    }
    out << '"';
    return out.str();
}
}

SCSFExport scsf_SierraMCPBridge(SCStudyInterfaceRef sc)
{
    SCInputRef OutputPath = sc.Input[0];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Sierra MCP Bridge";
        sc.StudyDescription = "Exports latest-bar price, bar VWAP, volume and footprint to JSON for FastMCP. Use a unique output path per chart.";
        sc.AutoLoop = 0;
        sc.GraphRegion = 0;
        sc.MaintainVolumeAtPriceData = 1;
        sc.CalculationPrecedence = VERY_LOW_PREC_LEVEL;
        OutputPath.Name = "Snapshot output path (unique per study instance)";
        OutputPath.SetString("");
        sc.Input[9].Name = "Reset export identity once (for copied studies; save chartbook afterward)";
        sc.Input[9].SetYesNo(0);
        for (int slot = 1; slot <= 8; ++slot)
        {
            sc.Input[slot].Name.Format("Export study/subgraph %d (study ID 0 disables)", slot);
            sc.Input[slot].SetStudySubgraphValues(0, 0);
        }
        return;
    }

    void*& writerPointer = sc.GetPersistentPointer(10);
    if (sc.LastCallToFunction)
    {
        delete static_cast<ExportWriter*>(writerPointer);
        writerPointer = nullptr;
        return;
    }
    int idx = sc.ArraySize - 1;
    if (idx < 0) return;

    const bool reset = sc.Input[9].GetYesNo() != 0;
    if (reset)
    {
        delete static_cast<ExportWriter*>(writerPointer);
        writerPointer = nullptr;
    }
    int& identityError = sc.GetPersistentInt(10);
    if (!EnsureExportIdentity(sc.StorageBlock, reset))
    {
        if (!identityError) sc.AddMessageToLog("Sierra MCP Bridge: export identity unavailable or invalid; export stopped.", 1);
        identityError = 1;
        return;
    }
    if (reset) sc.Input[9].SetYesNo(0);
    ExportIdentity identity;
    std::memcpy(&identity, sc.StorageBlock, sizeof(identity));
    const std::string directory = std::string(sc.DataFilesFolder().GetChars()) + "\\SierraMCPBridge";
    std::string path = OutputPath.GetString();
    if (path.empty()) path = directory + "\\mcp_" + identity.id + ".json";
    ExportWriter* writer = static_cast<ExportWriter*>(writerPointer);
    if (writer && (writer->path != path || writer->id != identity.id))
    {
        delete writer;
        writer = nullptr;
        writerPointer = nullptr;
    }
    if (!writer)
    {
        const bool directoryReady = CreateDirectoryA(directory.c_str(), nullptr) != 0 || GetLastError() == ERROR_ALREADY_EXISTS;
        writer = new ExportWriter;
        if (!directoryReady || !writer->Claim(directory, identity.id, path))
        {
            delete writer;
            if (!identityError) sc.AddMessageToLog("Sierra MCP Bridge: cannot claim export identity/path. Check directory permissions, duplicate bridge instances and copied study identities. No snapshot written.", 1);
            identityError = 1;
            return;
        }
        writerPointer = writer;
        SCString message;
        message.Format("Sierra MCP Bridge: claimed export %s at %s. Save the chartbook to persist identity.", identity.id, path.c_str());
        sc.AddMessageToLog(message, 0);
    }
    identityError = 0;

    int& invalidLogged = sc.GetPersistentInt(2);
    if (!std::isfinite(sc.Close[idx]) || !std::isfinite(sc.Volume[idx]) || sc.Volume[idx] < 0
        || !std::isfinite(sc.TickSize) || !std::isfinite(sc.BaseDateTimeIn[idx].GetAsDouble()))
    {
        if (!invalidLogged)
            sc.AddMessageToLog("Sierra MCP Bridge: invalid/nonfinite chart value; preserving previous snapshot.", 1);
        invalidLogged = 1;
        return;
    }
    invalidLogged = 0;

    // VWAP is for the latest bar only. VAP provenance remains unverified.
    // A missing/empty footprint produces null VWAP rather than a fabricated value.
    double priceVolume = 0.0;
    double vapVolume = 0.0;
    std::ostringstream footprint;
    footprint.imbue(std::locale::classic());
    footprint << std::setprecision(15);
    bool first = true;
    const unsigned int levels = sc.VolumeAtPriceForBars && sc.TickSize > 0
        ? sc.VolumeAtPriceForBars->GetSizeAtBarIndex(idx) : 0;
    for (unsigned int level = 0; level < levels; ++level)
    {
        const s_VolumeAtPriceV2* vap = nullptr;
        if (!sc.VolumeAtPriceForBars->GetVAPElementAtIndex(idx, level, &vap) || !vap)
            continue;
        const double price = vap->PriceInTicks * static_cast<double>(sc.TickSize);
        priceVolume += price * vap->Volume;
        vapVolume += vap->Volume;
        if (!first) footprint << ',';
        first = false;
        footprint << "\n    {\"price\": " << price
            << ", \"volume\": " << vap->Volume
            << ", \"bid_volume\": " << vap->BidVolume
            << ", \"ask_volume\": " << vap->AskVolume
            << ", \"delta\": " << static_cast<double>(vap->AskVolume) - static_cast<double>(vap->BidVolume) << '}';
    }

    std::ostringstream studies;
    SCFloatArray selectedValues[8];
    unsigned int selectedIDs[8] = {};
    unsigned int selectedSubgraphs[8] = {};
    bool selectedAvailable[8] = {};
    studies.imbue(std::locale::classic());
    studies << std::setprecision(15);
    bool firstStudy = true;
    for (int slot = 1; slot <= 8; ++slot)
    {
        const unsigned int studyID = sc.Input[slot].GetStudyID();
        const unsigned int subgraph = sc.Input[slot].GetSubgraphIndex();
        if (studyID == 0) continue;
        bool duplicate = false;
        for (int previous = 1; previous < slot; ++previous)
            if (sc.Input[previous].GetStudyID() == studyID
                && sc.Input[previous].GetSubgraphIndex() == subgraph) duplicate = true;
        if (duplicate) continue;
        SCFloatArray& values = selectedValues[slot - 1];
        selectedIDs[slot - 1] = studyID;
        selectedSubgraphs[slot - 1] = subgraph;
        selectedAvailable[slot - 1] = sc.GetStudyArrayUsingID(studyID, subgraph, values) != 0;
        const bool available = selectedAvailable[slot - 1] && values.GetArraySize() > idx;
        if (!firstStudy) studies << ',';
        firstStudy = false;
        const SCString studyName = sc.GetStudyNameUsingID(studyID);
        const char* subgraphName = sc.GetStudySubgraphName(studyID, subgraph);
        studies << "{\"study_id\":" << studyID << ",\"subgraph_index\":" << subgraph
            << ",\"study_name\":" << JsonString(studyName.GetChars())
            << ",\"subgraph_name\":" << JsonString(subgraphName ? subgraphName : "")
            << ",\"metadata\":" << StudyMetadata(sc, studyID, subgraph, idx) << ",\"value\":";
        if (!available)
            studies << "null,\"reason\":\"study_unavailable\"}";
        else if (!std::isfinite(values[idx]))
            studies << "null,\"reason\":\"nonfinite_value\"}";
        else
            studies << values[idx] << ",\"reason\":null}";
    }

    // Rolling loaded-chart window, oldest first, including the current forming bar.
    // Fetch study arrays once above; never ask Sierra to download historical data here.
    std::ostringstream history;
    history.imbue(std::locale::classic());
    history << std::setprecision(15);
    const int start = idx >= 199 ? idx - 199 : 0;
    for (int bar = start; bar <= idx; ++bar)
    {
        if (bar != start) history << ',';
        int year, month, day, hour, minute, second, microsecond;
        sc.BaseDateTimeIn[bar].GetDateTimeYMDHMS_US(year, month, day, hour, minute, second, microsecond);
        SCString timestamp;
        timestamp.Format("%04d-%02d-%02dT%02d:%02d:%02d.%06d", year, month, day, hour, minute, second, microsecond);
        history << "{\"bar_index\":" << bar
            << ",\"bar_start_sc_datetime\":" << sc.BaseDateTimeIn[bar].GetAsDouble()
            << ",\"bar_start_chart_time\":" << JsonString(timestamp.GetChars())
            << ",\"is_closed\":" << (sc.GetBarHasClosedStatus(bar) == BHCS_BAR_HAS_CLOSED ? "true" : "false")
            << ",\"open\":" << JsonNumber(sc.Open[bar])
            << ",\"high\":" << JsonNumber(sc.High[bar])
            << ",\"low\":" << JsonNumber(sc.Low[bar])
            << ",\"close\":" << JsonNumber(sc.Close[bar])
            << ",\"volume\":" << (sc.Volume[bar] < 0 ? "null" : JsonNumber(sc.Volume[bar]))
            << ",\"studies\":[";
        bool firstValue = true;
        for (int slot = 0; slot < 8; ++slot)
        {
            if (selectedIDs[slot] == 0) continue;
            if (!firstValue) history << ',';
            firstValue = false;
            history << "{\"study_id\":" << selectedIDs[slot]
                << ",\"subgraph_index\":" << selectedSubgraphs[slot] << ",\"value\":";
            if (!selectedAvailable[slot] || selectedValues[slot].GetArraySize() <= bar)
                history << "null,\"reason\":\"study_unavailable\"}";
            else if (!std::isfinite(selectedValues[slot][bar]))
                history << "null,\"reason\":\"nonfinite_value\"}";
            else
                history << selectedValues[slot][bar] << ",\"reason\":null}";
        }
        history << "]}";
    }

    const std::string tempPath = path + "." + identity.id + ".tmp";
    std::ofstream json_out(tempPath, std::ios::binary | std::ios::trunc);
    json_out.imbue(std::locale::classic());
    const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    n_ACSIL::s_BarPeriod period;
    sc.GetBarPeriodParameters(period);
    json_out << std::setprecision(15)
        << "{\n  \"schema_version\": 1,\n"
        << "  \"exporter_revision\": \"1.6\",\n"
        << "  \"export_id\": " << JsonString(identity.id) << ",\n"
        << "  \"chart_timezone\": " << JsonString(sc.GetChartTimeZone(sc.ChartNumber).GetChars()) << ",\n"
        << "  \"bar_period\": {\"chart_data_type\":" << static_cast<int>(period.ChartDataType)
        << ",\"intraday_bar_period_type\":" << static_cast<int>(period.IntradayChartBarPeriodType)
        << ",\"parameters\":[" << period.IntradayChartBarPeriodParameter1
        << ',' << period.IntradayChartBarPeriodParameter2
        << ',' << period.IntradayChartBarPeriodParameter3
        << ',' << period.IntradayChartBarPeriodParameter4
        << "],\"historical_bar_period_type\":" << static_cast<int>(period.HistoricalChartBarPeriodType)
        << ",\"historical_days_per_bar\":" << period.HistoricalChartDaysPerBar << "},\n"
        << "  \"snapshot_time_unix_ms\": " << now << ",\n"
        << "  \"chart_number\": " << sc.ChartNumber << ",\n"
        << "  \"bar_index\": " << idx << ",\n"
        << "  \"bar_start_sc_datetime\": " << sc.BaseDateTimeIn[idx].GetAsDouble() << ",\n"
        << "  \"symbol\": " << JsonString(sc.Symbol.GetChars()) << ",\n"
        << "  \"last_price\": " << sc.Close[idx] << ",\n"
        << "  \"vwap_scope\": \"current_bar\",\n"
        << "  \"vwap\": ";
    if (vapVolume > 0) json_out << priceVolume / vapVolume;
    else json_out << "null";
    json_out << ",\n  \"volume\": " << sc.Volume[idx]
        << ",\n  \"footprint_volume\": " << vapVolume
        << ",\n  \"footprint\": [" << footprint.str() << "\n  ],\n"
        << "  \"studies\": [" << studies.str() << "],\n"
        << "  \"history\": [" << history.str() << "]\n}\n";
    json_out.close();

    // Keep the previous complete snapshot if writing or replacement fails.
    int& errorLogged = sc.GetPersistentInt(1);
    if (!json_out || !MoveFileExA(tempPath.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING))
    {
        if (!errorLogged)
            sc.AddMessageToLog("Sierra MCP Bridge: snapshot write/replace failed. Check the output directory and reader file locks. Will retry on the next chart update.", 1);
        errorLogged = 1;
    }
    else errorLogged = 0;
}
