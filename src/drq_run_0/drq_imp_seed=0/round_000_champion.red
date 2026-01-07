
;name       Bouncer
;author     ChatGPT
;strategy   A simple "Bouncer" warrior that moves a bomb back and forth between two memory locations.
;           It hits one target, then moves to the other, continuously bouncing and bombing.

        ORG     start

step    EQU     8                   ; Distance to move the bomb each bounce
pos     DAT.F   #0, #0             ; Current bomb position pointer (initialized to 0)

start   MOV.I   pos, bomb          ; Set initial bomb position
bounce  ADD.AB #step, pos          ; Move pointer by step
        JMZ     reset, pos         ; If pos zero (wrap around), reset to start
        MOV.I   bomb, @pos         ; Bomb current target
        JMP     bounce

reset   DAT.F   #0, #0             ; Reset the pointer to zero
        JMP     bounce

bomb    DAT.F   #0, #0             ; Bomb instruction (kills the process where dropped)

        END     start
