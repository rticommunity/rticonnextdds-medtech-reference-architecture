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

    id nsdata = ((id(*)(Class, SEL, const void *, unsigned long))objc_msgSend)(
        objc_getClass("NSData"),
        sel_registerName("dataWithBytes:length:"),
        buf, (unsigned long)buf_size);

    id nsimage = ((id(*)(id, SEL))objc_msgSend)(
        (id)objc_getClass("NSImage"),
        sel_registerName("alloc"));
    nsimage = ((id(*)(id, SEL, id))objc_msgSend)(
        nsimage,
        sel_registerName("initWithData:"),
        nsdata);

    id nsapp = ((id(*)(Class, SEL))objc_msgSend)(
        objc_getClass("NSApplication"),
        sel_registerName("sharedApplication"));
    ((void(*)(id, SEL, id))objc_msgSend)(
        nsapp,
        sel_registerName("setApplicationIconImage:"),
        nsimage);

    g_free(buf);
}

#endif // __APPLE__
