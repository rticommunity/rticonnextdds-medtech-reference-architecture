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
#include <exception>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>

#ifdef RTI_DEMO_UI_NATIVE_AVAILABLE
    #include <rti_demo_ui_native/native_webview.hpp>
#endif

namespace medtech::ui {

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

inline void run(rti::demo::ui::DemoUiApp &app,
                [[maybe_unused]] int native_width = 1280,
                [[maybe_unused]] int native_height = 800)
{
    if (native_mode()) {
#ifdef RTI_DEMO_UI_NATIVE_AVAILABLE
        rti::demo::ui::native::run(app,
                                   rti::demo::ui::native::NativeWindowOptions {
                                           native_width,
                                           native_height,
                                   });
        return;
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
    std::exception_ptr server_error;
    std::thread server([&]() {
        try {
            app.run();
        } catch (...) {
            server_error = std::current_exception();
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
        if (server_error)
            std::rethrow_exception(server_error);
        throw std::runtime_error("RTI Demo UI server did not become ready");
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
    if (server_error)
        std::rethrow_exception(server_error);
}

}  // namespace medtech::ui
