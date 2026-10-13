//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
#pragma once

#include <mutex>
#include <optional>
#include <queue>
#include <utility>

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

}  // namespace medtech::ui
