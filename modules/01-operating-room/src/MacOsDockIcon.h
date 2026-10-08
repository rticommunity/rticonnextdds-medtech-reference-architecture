//
// (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
//
// RTI grants Licensee a license to use, modify, compile, and create derivative
// works of the software solely for use with RTI Connext DDS.  Licensee may
// redistribute copies of the software provided that all such copies are
// subject to this license. The software is provided "as is", with no warranty
// of any type, including any warranty for fitness for any purpose. RTI is
// under no obligation to maintain or support the software.  RTI shall not be
// liable for any incidental or consequential damages arising out of the use or
// inability to use the software.

#pragma once
#ifdef __APPLE__

    #include <gdkmm/pixbuf.h>
    #include <objc/objc.h>
    #include <objc/message.h>

// Set the macOS Dock icon from a GdkPixbuf.
// GTK's set_icon() only affects the window decoration, not the Dock.
// This uses the native NSApplication API to set the application icon.
inline void set_macos_dock_icon(const Glib::RefPtr<Gdk::Pixbuf> &pb)
{
    if (!pb)
        return;

    // Write pixbuf to an in-memory PNG buffer
    gchar *buf = nullptr;
    gsize buf_size = 0;
    pb->save_to_buffer(buf, buf_size, "png");
    if (!buf || buf_size == 0)
        return;

    // Use Objective-C runtime to call:
    //   NSImage *img = [[NSImage alloc] initWithData:
    //       [NSData dataWithBytes:buf length:buf_size]];
    //   [[NSApplication sharedApplication] setApplicationIconImage:img];

    id nsdata =
            ((id (*)(Class, SEL, const void *, unsigned long)) objc_msgSend)(
                    objc_getClass("NSData"),
                    sel_registerName("dataWithBytes:length:"),
                    buf,
                    (unsigned long) buf_size);

    id nsimage = ((id (*)(id, SEL)) objc_msgSend)((id) objc_getClass("NSImage"),
                                                  sel_registerName("alloc"));
    nsimage = ((id (*)(id, SEL, id)) objc_msgSend)(
            nsimage,
            sel_registerName("initWithData:"),
            nsdata);

    id nsapp = ((id (*)(Class, SEL)) objc_msgSend)(
            objc_getClass("NSApplication"),
            sel_registerName("sharedApplication"));
    ((void (*)(id, SEL, id)) objc_msgSend)(
            nsapp,
            sel_registerName("setApplicationIconImage:"),
            nsimage);

    g_free(buf);
}

#endif  // __APPLE__
