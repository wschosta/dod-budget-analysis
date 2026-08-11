"""Package entry point: ``python -m downloader``.

``downloader/__init__.py`` re-exports from ``downloader.core``, so running
``python -m downloader.core`` imports the module twice and Python emits a
RuntimeWarning about unpredictable behaviour.  Routing the CLI through the
package's ``__main__`` avoids that: the package is imported once, normally,
and only then is ``main()`` called.
"""

from downloader.core import main

if __name__ == "__main__":
    main()
