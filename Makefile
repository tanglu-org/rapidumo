PREFIX := /usr

install: $(scripts)
	echo "IMPORTANT! We don't really install anything, we just create a symlink."
	ln -sf $(shell readlink -f ./synctool/sync-debian-package.py) $(DESTDIR)/usr/bin/sync-debian-package

clean:
	rm -f *.pyc

.PHONY: install clean
