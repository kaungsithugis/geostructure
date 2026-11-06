def classFactory(iface):
    from .plugin import GeologyViewer
    return GeologyViewer(iface)
