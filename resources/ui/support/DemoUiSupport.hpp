//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
// RTI grants Licensee a license to use, modify, compile, and create derivative
// works of the software solely for use with RTI Connext DDS. The software is
// provided "as is", with no warranty of any type.
#pragma once

#include <rti_demo_ui/rti_demo_ui.hpp>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <optional>
#include <queue>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <utility>

#ifdef RTI_DEMO_UI_NATIVE_AVAILABLE
    #include <rti_demo_ui_native/native_webview.hpp>
#endif

namespace medtech::ui {

template <typename Command>
class CommandQueue {
public:
    void push(Command command)
    {
        std::lock_guard<std::mutex> guard(mutex_);
        commands_.push(std::move(command));
    }

    std::optional<Command> try_pop()
    {
        std::lock_guard<std::mutex> guard(mutex_);
        if (commands_.empty())
            return std::nullopt;
        Command command = std::move(commands_.front());
        commands_.pop();
        return command;
    }

private:
    std::mutex mutex_;
    std::queue<Command> commands_;
};

inline volatile std::sig_atomic_t stop_signal = 0;

inline void request_stop(int signal_number)
{
    stop_signal = signal_number;
}

inline bool is_model_stopped_error(const std::runtime_error &error)
{
    return std::string_view(error.what()) == "DemoUiApp: model is stopped";
}

inline bool native_mode()
{
    const char *value = std::getenv("RTI_DEMO_UI_MODE");
    if (value == nullptr || std::string(value) == "browser")
        return false;
    if (std::string(value) == "native")
        return true;
    throw std::runtime_error(
            "Unknown RTI_DEMO_UI_MODE; choose browser or native");
}

inline std::filesystem::path native_icon_path()
{
#ifdef _WIN32
    return std::filesystem::path(RTI_DEMO_UI_WEB_ROOT) / "rti_logo.ico";
#else
    return std::filesystem::path(RTI_DEMO_UI_WEB_ROOT) / "rti_logo.png";
#endif
}

inline bool run(rti::demo::ui::DemoUiApp &app,
                [[maybe_unused]] int native_width = 1280,
                [[maybe_unused]] int native_height = 800,
                [[maybe_unused]] std::filesystem::path native_icon = { })
{
    if (native_mode()) {
#ifdef RTI_DEMO_UI_NATIVE_AVAILABLE
        rti::demo::ui::native::NativeWindowOptions options;
        options.width = native_width;
        options.height = native_height;
        options.icon = std::move(native_icon);
        rti::demo::ui::native::run(app, std::move(options));
        return true;
#else
        throw std::runtime_error(
                "Native UI mode is not enabled in this build; configure CMake "
                "with -DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON");
#endif
    }

    const auto previous_int = std::signal(SIGINT, request_stop);
    const auto previous_term = std::signal(SIGTERM, request_stop);
    stop_signal = 0;
    std::atomic<bool> finished = false;
    bool server_failed = false;
    std::thread server([&]() {
        try {
            app.run();
        } catch (const std::exception &error) {
            std::cerr << "RTI Demo UI server failed: " << error.what()
                      << std::endl;
            server_failed = true;
        } catch (...) {
            std::cerr << "RTI Demo UI server failed with an unknown exception"
                      << std::endl;
            server_failed = true;
        }
        finished.store(true);
    });

    const auto startup_deadline =
            std::chrono::steady_clock::now() + std::chrono::seconds(10);
    std::optional<rti::demo::ui::ReadyInfo> ready;
    while (!finished.load()
           && std::chrono::steady_clock::now() < startup_deadline) {
        ready = app.ready_info();
        if (ready.has_value())
            break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    if (!ready.has_value()) {
        app.stop();
        server.join();
        std::signal(SIGINT, previous_int);
        std::signal(SIGTERM, previous_term);
        if (!server_failed)
            std::cerr << "RTI Demo UI server did not become ready" << std::endl;
        return false;
    }

    std::thread signal_monitor([&]() {
        while (!finished.load()) {
            if (stop_signal != 0) {
                app.stop();
                return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    });
    server.join();
    finished.store(true);
    signal_monitor.join();
    std::signal(SIGINT, previous_int);
    std::signal(SIGTERM, previous_term);
    return !server_failed;
}

}  // namespace medtech::ui
