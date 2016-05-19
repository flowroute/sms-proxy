# Not Ubuntu or python.  Saves lots of image size and decreases attack surface.
FROM alpine

# This is where the app is going to live.
WORKDIR /app
# Expose the service API endpoint.
EXPOSE 8000

ENV APP sms_proxy

# We're not going to be root.
RUN mkdir -p /app/$APP \
 && touch /app/$APP/__init__.py

# Don't copy the whole app yet, as that invalidates the cache for further
# layers.  As long as these files don't change, the following layers with pip
# install can be cached...
# Note:  We're not copying in the .git files, so version.txt is what vcversioner
# is going to want to see.
COPY setup.py requirements.txt /app/

# apk allows bundling a virtual package to uninstall, to cleanup the image.
# Here, we're installing what we need to build python modules (including C
# extensions), then removing that at the end, as we don't want those in the
# image, once the modules are finished installing.
#
# Note that the setup.py check line ensures that vcversion is happy.
RUN apk --update add \
    libffi \
    libffi-dev \
    openssl \
    py-cryptography \
    py-virtualenv \
    ca-certificates
RUN apk --update add --virtual build-deps \
    build-base \
    git \
    libev-dev \
    openssl-dev \
    python-dev \
    wget \
 && virtualenv /app/ve \
 && /app/ve/bin/pip install -U pip \
 && /app/ve/bin/python /app/setup.py check \
 && /app/ve/bin/pip install -r /app/requirements.txt \
 && apk del build-deps

# Finally copy the app, at the very end so we can cycle very quickly.
COPY . /app
ENTRYPOINT ["/app/entry"]
CMD ["serve"]
