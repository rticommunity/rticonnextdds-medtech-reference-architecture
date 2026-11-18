//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
// RTI grants Licensee a license to use, modify, compile, and create derivative
// works of the software solely for use with RTI Connext DDS. The software is
// provided "as is", with no warranty of any type.

#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <functional>
#include <iostream>
#include <map>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

#include <dds/core/cond/StatusCondition.hpp>
#include <dds/core/policy/CorePolicy.hpp>
#include <dds/domain/DomainParticipant.hpp>
#include <dds/sub/DataReader.hpp>
#include <dds/sub/Subscriber.hpp>
#include <dds/sub/cond/ReadCondition.hpp>
#include <dds/pub/DataWriter.hpp>
#include <rti/core/cond/AsyncWaitSet.hpp>

#include "MedTech.hpp"

namespace medtech::operating_room {

template <typename T>
std::chrono::nanoseconds heartbeat_period_from_deadline(
        const ::dds::pub::DataWriter<T> &writer)
{
    const auto deadline =
            writer.qos()
                    .template policy<::dds::core::policy::Deadline>()
                    .period();
    if (deadline == ::dds::core::Duration::infinite()
        || deadline <= ::dds::core::Duration::zero()) {
        throw std::runtime_error(
                "Heartbeat writer deadline must be finite and positive");
    }

    const auto deadline_nanoseconds = deadline.to_nanosecs();
    if (deadline_nanoseconds < 3) {
        throw std::runtime_error(
                "Heartbeat writer deadline must be at least 3 nanoseconds");
    }

    return std::chrono::nanoseconds(deadline_nanoseconds / 3);
}

class HeartbeatPublisher {
public:
    HeartbeatPublisher(const dds::pub::DataWriter<Device::Heartbeat> &writer,
                       Device::DeviceType device)
            : writer_(writer),
              sample_(device),
              period_(heartbeat_period_from_deadline(writer_))
    {
    }

    HeartbeatPublisher(const HeartbeatPublisher &) = delete;
    HeartbeatPublisher &operator=(const HeartbeatPublisher &) = delete;

    ~HeartbeatPublisher()
    {
        stop();
    }

    void start()
    {
        if (worker_.joinable() || stopping_)
            throw std::logic_error(
                    "Heartbeat publisher has already been started or stopped");
        worker_ = std::thread([this]() {
            try {
                std::unique_lock<std::mutex> lock(mutex_);
                auto next = std::chrono::steady_clock::now();
                while (!stopping_) {
                    lock.unlock();
                    writer_.write(sample_);
                    lock.lock();
                    next += period_;
                    const auto now = std::chrono::steady_clock::now();
                    if (next <= now)
                        next = now + period_;
                    wake_.wait_until(lock, next, [this]() {
                        return stopping_;
                    });
                }
            } catch (const std::exception &error) {
                std::cerr << "Heartbeat publisher failed: " << error.what()
                          << std::endl;
                failed_ = true;
            } catch (...) {
                std::cerr << "Heartbeat publisher failed with an unknown "
                             "exception"
                          << std::endl;
                failed_ = true;
            }
        });
    }

    void stop()
    {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
        }
        wake_.notify_one();
        if (worker_.joinable())
            worker_.join();
    }

    bool failed() const
    {
        return failed_;
    }

private:
    dds::pub::DataWriter<Device::Heartbeat> writer_;
    Device::Heartbeat sample_;
    std::chrono::nanoseconds period_;
    std::mutex mutex_;
    std::condition_variable wake_;
    bool stopping_ = false;
    std::atomic<bool> failed_ { false };
    std::thread worker_;
};

class HeartbeatPresenceMonitor {
public:
    using PresenceHandler = std::function<void(Device::DeviceType, bool)>;

    HeartbeatPresenceMonitor(
            const dds::sub::DataReader<Device::Heartbeat> &reader,
            PresenceHandler presence_handler)
            : reader_(reader),
              participant_(reader_.subscriber().participant()),
              deadline_(reader_.qos()
                                .policy<dds::core::policy::Deadline>()
                                .period()),
              deadline_condition_(reader_),
              data_condition_(reader_, dds::sub::status::DataState::new_data()),
              presence_handler_(std::move(presence_handler))
    {
        for (const auto device : {
                     Device::DeviceType::ARM,
                     Device::DeviceType::ARM_CONTROLLER,
                     Device::DeviceType::PATIENT_SENSOR,
                     Device::DeviceType::PATIENT_MONITOR,
             }) {
            presence_[device] = false;
        }

        deadline_condition_.enabled_statuses(
                dds::core::status::StatusMask::requested_deadline_missed());
        deadline_condition_.extensions().handler(
                [this]() { handle_deadline_missed(); });
        data_condition_.extensions().handler([this]() { handle_new_data(); });
        waitset_.attach_condition(deadline_condition_);
        waitset_.attach_condition(data_condition_);
    }

    HeartbeatPresenceMonitor(const HeartbeatPresenceMonitor &) = delete;
    HeartbeatPresenceMonitor &operator=(const HeartbeatPresenceMonitor &) =
            delete;

    ~HeartbeatPresenceMonitor() noexcept
    {
        try {
            stop();
        } catch (const std::exception &error) {
            std::cerr << "Heartbeat presence shutdown failed: " << error.what()
                      << std::endl;
            std::terminate();
        } catch (...) {
            std::cerr << "Heartbeat presence shutdown failed with an unknown "
                         "exception"
                      << std::endl;
            std::terminate();
        }
    }

    void start()
    {
        waitset_.start();
    }

    void stop()
    {
        waitset_.stop();
    }

private:
    using Transition = std::pair<Device::DeviceType, bool>;

    void update_presence(Device::DeviceType device,
                         bool is_present,
                         std::vector<Transition> &transitions)
    {
        const auto found = presence_.find(device);
        if (found == presence_.end() || found->second == is_present)
            return;

        found->second = is_present;
        transitions.emplace_back(device, is_present);
    }

    void notify_transitions(const std::vector<Transition> &transitions)
    {
        for (const auto &[device, is_present] : transitions) {
            presence_handler_(device, is_present);
        }
    }

    bool is_recent(const dds::core::Time &reception_time,
                   const dds::core::Time &now) const
    {
        return deadline_ == dds::core::Duration::infinite()
                || now < reception_time || now - reception_time < deadline_;
    }

    template <typename Samples>
    void process_samples(const Samples &samples,
                         const dds::core::Time &now,
                         std::vector<Transition> &transitions)
    {
        for (const auto &sample : samples) {
            if (!sample.info().valid())
                continue;

            const auto device = sample.data().device;
            if (presence_.find(device) == presence_.end())
                continue;

            const auto reception_time =
                    sample.info().extensions().reception_timestamp();
            const auto previous = last_reception_.find(device);
            if (previous == last_reception_.end()
                || previous->second < reception_time) {
                last_reception_[device] = reception_time;
            }
            update_presence(device,
                            is_recent(last_reception_.at(device), now),
                            transitions);
        }
    }

    void handle_deadline_missed()
    {
        std::vector<Transition> transitions;
        try {
            {
                std::lock_guard<std::mutex> guard(mutex_);
                const auto status = reader_.requested_deadline_missed_status();
                if (status.total_count_change() == 0)
                    return;

                const auto samples =
                        reader_.select()
                                .state(dds::sub::status::DataState::new_data())
                                .take();
                const auto now = participant_.current_time();
                process_samples(samples, now, transitions);

                for (const auto &[device, reception_time] : last_reception_) {
                    update_presence(device,
                                    is_recent(reception_time, now),
                                    transitions);
                }
            }
            notify_transitions(transitions);
        } catch (const std::exception &error) {
            std::cerr << "Heartbeat deadline handler failed: " << error.what()
                      << std::endl;
        } catch (...) {
            std::cerr << "Heartbeat deadline handler failed with an "
                         "unknown exception"
                      << std::endl;
        }
    }

    void handle_new_data()
    {
        std::vector<Transition> transitions;
        try {
            {
                std::lock_guard<std::mutex> guard(mutex_);
                const auto samples =
                        reader_.select().condition(data_condition_).take();
                process_samples(samples,
                                participant_.current_time(),
                                transitions);
            }
            notify_transitions(transitions);
        } catch (const std::exception &error) {
            std::cerr << "Heartbeat data handler failed: " << error.what()
                      << std::endl;
        } catch (...) {
            std::cerr << "Heartbeat data handler failed with an unknown "
                         "exception"
                      << std::endl;
        }
    }

    dds::sub::DataReader<Device::Heartbeat> reader_;
    dds::domain::DomainParticipant participant_;
    dds::core::Duration deadline_;
    dds::core::cond::StatusCondition deadline_condition_;
    dds::sub::cond::ReadCondition data_condition_;
    rti::core::cond::AsyncWaitSet waitset_;
    PresenceHandler presence_handler_;
    std::mutex mutex_;
    std::map<Device::DeviceType, dds::core::Time> last_reception_;
    std::map<Device::DeviceType, bool> presence_;
};

}  // namespace medtech::operating_room
