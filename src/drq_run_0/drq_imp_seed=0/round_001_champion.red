
;name Clockwork
;author ChatGPT
;strategy A simple multi-tasking "clock" that increments a counter forever, splitting every cycle
; This warrior keeps a count in 'counter', increments it, then splits to run the increment loop concurrently.

        ORG start

counter DAT #0, #0               ; holds the cycle count

start   SPL worker               ; spawn a worker to increment the counter
        JMP start               ; loop forever spawning workers

worker  ADD #1, counter         ; increment counter
        SPL worker              ; spawn another worker to keep incrementing
        JMP end_worker          ; end this task

end_worker NOP                   ; do nothing and finish

        END
