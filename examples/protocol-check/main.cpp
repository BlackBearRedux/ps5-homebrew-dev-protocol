// SPDX-License-Identifier: GPL-3.0-or-later
#include "demo_renderer.hpp"
#include <array>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <cstdint>

extern "C" {
int sceKernelOpen(const char *, int, int);
int sceKernelClose(int);
std::int64_t sceKernelRead(int, void *, std::size_t);
std::int64_t sceKernelWrite(int, const void *, std::size_t);
int sceKernelDebugOutText(int, const char *);
}

namespace {
constexpr char command[] = "/download0/protocol-command.txt";
constexpr char report[] = "/download0/protocol-log.txt";
constexpr char build[] = "PROTOCOL CHECK V1";
unsigned frame = 0;
bool changed = false;

bool record(const char *line, bool reset = false)
{
    (void)sceKernelDebugOutText(0, line);
    int fd = sceKernelOpen(report, O_WRONLY | O_CREAT | (reset ? O_TRUNC : O_APPEND), 0666);
    if (fd < 0) return false;
    const auto len = std::strlen(line);
    const bool ok = sceKernelWrite(fd, line, len) == static_cast<std::int64_t>(len);
    return sceKernelClose(fd) == 0 && ok;
}

bool advance_requested()
{
    int fd = sceKernelOpen(command, O_RDONLY, 0);
    if (fd < 0) return false;
    std::array<char, 16> bytes{};
    auto count = sceKernelRead(fd, bytes.data(), bytes.size());
    sceKernelClose(fd);
    return count == 5 && std::memcmp(bytes.data(), "NEXT\n", 5) == 0;
}

void draw(ps5::demo::Canvas &canvas) noexcept
{
    using ps5::demo::Color;
    ++frame;
    const bool advance = !changed && frame > 12 && frame % 8 == 0 && advance_requested();
    if (advance) changed = true;
    canvas.clear(Color::background);
    canvas.text(140, 120, build, 9, Color::white);
    canvas.text(140, 360, changed ? "INPUT RECEIVED" : "WAITING FOR INPUT", 7, Color::white);
    canvas.rectangle(140, 570, 320, 180, changed ? Color::yellow : Color::cyan);
    if (frame == 12 || advance) {
        const bool ok = canvas.save_ppm(changed ? "/download0/after.ppm" : "/download0/before.ppm");
        record(ok ? (changed ? "PROTOCOL INPUT SAVED\n" : "PROTOCOL READY\n") : "PROTOCOL CAPTURE FAILED\n");
    }
}
}

int main()
{
    int fd = sceKernelOpen(command, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0 || sceKernelClose(fd) != 0 || !record("PROTOCOL START V1\n", true)) {
        (void)sceKernelDebugOutText(0, "PROTOCOL START FAILED\n");
        return 1;
    }
    ps5::demo::run_frames(draw, build);
}
