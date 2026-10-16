"""Domain errors.

These exist so infrastructure failures are *typed* rather than swallowed. The
graph reacts to them by holding the flight, never by inventing a result.
"""


class NotamGuardError(Exception):
    """Base class for all recoverable failures in the pipeline."""


class RetrievalUnavailable(NotamGuardError):
    """The vector store could not be queried.

    Deliberately fatal to the ALLOW path: a compliance gate that cannot read the
    regulations must not clear a flight.
    """


class NotamSourceUnavailable(NotamGuardError):
    """The NOTAM corpus could not be read or contained no usable entries."""


class TicketStoreUnavailable(NotamGuardError):
    """The ticket store could not be reached or refused the request (for example
    DynamoDB throttling a flood).

    The verdict does not depend on it: a flight that needs a person stays held or
    blocked whether or not a ticket could be opened.
    """
