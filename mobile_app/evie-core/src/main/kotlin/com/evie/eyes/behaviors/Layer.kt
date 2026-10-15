package com.evie.eyes.behaviors

import com.evie.eyes.model.EyeParams

/** Camada procedural: `update(dt)` avança o estado e `apply` soma o efeito nos dois olhos. */
interface Layer {
    fun update(dt: Double)
    fun apply(left: EyeParams, right: EyeParams)
}
